<?php
/**
 * CAPI Gateway — Frontend Tracking
 *
 * ওয়েবসাইটের ফ্রন্টএন্ডে অটোমেটিক ইভেন্ট ট্র্যাকিং:
 * - PageView (প্রতিটি পেজে)
 * - ViewContent (WooCommerce প্রোডাক্ট পেজে)
 * - AddToCart (কার্টে যোগ করলে — AJAX দিয়ে)
 * - InitiateCheckout (চেকআউট পেজে)
 * - Purchase (Thank You / Order Received পেজে)
 *
 * Cache plugin bypass: সব ট্র্যাকিং AJAX/REST API দিয়ে চলে,
 * তাই LiteSpeed/WP Rocket ক্যাশ করলেও ডাটা ফ্রেশ থাকে।
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// ─── Inject Tracker Script ────────────────────────────────────────────────────
add_action( 'wp_footer', 'capigw_inject_tracker', 99 );

function capigw_inject_tracker() {
    $settings = capigw_get_settings();

    // Don't load if no API key
    if ( empty( $settings['api_key'] ) ) {
        return;
    }

    // Pass config to JS
    $tracker_data = array(
        'ajax_url'    => admin_url( 'admin-ajax.php' ),
        'nonce'       => wp_create_nonce( 'capigw_track_nonce' ),
        'events'      => array(
            'pageview'       => (bool) $settings['enable_pageview'],
            'lead'           => (bool) $settings['enable_lead'],
            'search'         => (bool) $settings['enable_search'],
            'viewcontent'    => (bool) $settings['enable_viewcontent'],
            'addtocart'      => (bool) $settings['enable_addtocart'],
            'viewcart'       => (bool) $settings['enable_viewcart'],
            'removefromcart' => (bool) $settings['enable_removefromcart'],
            'checkout'       => (bool) $settings['enable_checkout'],
            'addpaymentinfo' => (bool) $settings['enable_addpaymentinfo'],
            'purchase'       => (bool) $settings['enable_purchase'],
        ),
    );

    // Add product data if on a WooCommerce product page
    if ( function_exists( 'is_product' ) && is_product() && $settings['enable_viewcontent'] ) {
        global $product;
        if ( $product && is_a( $product, 'WC_Product' ) ) {
            $tracker_data['product'] = array(
                'id'       => $product->get_id(),
                'name'     => $product->get_name(),
                'price'    => (float) $product->get_price(),
                'currency' => get_woocommerce_currency(),
                'category' => implode( ', ', wp_list_pluck( wc_get_product_terms( $product->get_id(), 'product_cat' ), 'name' ) ),
            );
        }
    }

    // Detect page type
    $tracker_data['page_type'] = 'other';
    if ( function_exists( 'is_product' ) && is_product() ) {
        $tracker_data['page_type'] = 'product';
    } elseif ( function_exists( 'is_cart' ) && is_cart() ) {
        $tracker_data['page_type'] = 'cart';
    } elseif ( function_exists( 'is_checkout' ) && is_checkout() && ( ! function_exists( 'is_order_received_page' ) || ! is_order_received_page() ) ) {
        $tracker_data['page_type'] = 'checkout';
    } elseif ( function_exists( 'is_order_received_page' ) && is_order_received_page() ) {
        $tracker_data['page_type'] = 'thankyou';
    } elseif ( is_search() ) {
        $tracker_data['page_type'] = 'search';
        $tracker_data['search_string'] = get_search_query();
    }

    // Add cart data for ViewCart and InitiateCheckout matching/optimization.
    if (
        function_exists( 'WC' ) &&
        WC()->cart &&
        ( ( function_exists( 'is_cart' ) && is_cart() ) || ( function_exists( 'is_checkout' ) && is_checkout() && ( ! function_exists( 'is_order_received_page' ) || ! is_order_received_page() ) ) )
    ) {
        $cart_ids  = array();
        $num_items = 0;

        foreach ( WC()->cart->get_cart() as $cart_item ) {
            $product_id = isset( $cart_item['product_id'] ) ? (int) $cart_item['product_id'] : 0;
            if ( $product_id > 0 ) {
                $cart_ids[] = (string) $product_id;
            }
            $num_items += isset( $cart_item['quantity'] ) ? (int) $cart_item['quantity'] : 0;
        }

        $tracker_data['cart'] = array(
            'content_ids' => array_values( array_unique( $cart_ids ) ),
            'value'       => (float) WC()->cart->get_cart_contents_total(),
            'currency'    => get_woocommerce_currency(),
            'num_items'   => $num_items,
        );
    }

    echo "<script id='capigw-tracker-config'>\n";
    echo "window.capigw_config = " . wp_json_encode( $tracker_data ) . ";\n";
    echo "</script>\n";

    echo "<script id='capigw-tracker-js'>\n";
    echo capigw_get_tracker_js() . "\n";
    echo "</script>\n";
}

// ─── Tracker JavaScript ────────────────────────────────────────────────────────
function capigw_get_tracker_js() {
    return <<<'JS'
(function() {
    'use strict';

    var cfg = window.capigw_config || {};
    if (!cfg.ajax_url) return;
    persistTikTokClickId();

    // ─── Helper: Send event via AJAX (cache-safe) ──────────────────────
    function sendEvent(eventName, eventData, synchronous) {
        var formData = new FormData();
        formData.append('action', 'capigw_track_event');
        formData.append('nonce', cfg.nonce);
        formData.append('event_name', eventName);
        formData.append('event_data', JSON.stringify(eventData || {}));
        formData.append('page_url', window.location.href);
        formData.append('page_title', document.title);
        formData.append('fbp', getCookie('_fbp') || '');
        formData.append('fbc', getCookie('_fbc') || '');
        formData.append('ttp', getCookie('_ttp') || '');
        formData.append('ttclid', getTikTokClickId());

        // synchronous=true — পেজ নেভিগেট হওয়ার আগে নিশ্চিত পাঠাতে
        if (synchronous) {
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('POST', cfg.ajax_url, false); // false = sync
                xhr.send(formData);
            } catch(e) {}
            return;
        }

        if (navigator.sendBeacon) {
            navigator.sendBeacon(cfg.ajax_url, formData);
        } else {
            fetch(cfg.ajax_url, { method: 'POST', body: formData, keepalive: true });
        }
    }

    function getCookie(name) {
        var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        return match ? decodeURIComponent(match[2]) : '';
    }

    function getQueryParam(name) {
        try {
            return new URLSearchParams(window.location.search).get(name) || '';
        } catch(e) {
            return '';
        }
    }

    function persistTikTokClickId() {
        var ttclid = getQueryParam('ttclid');
        if (!ttclid) return;
        document.cookie = '_ttclid=' + encodeURIComponent(ttclid) + '; path=/; max-age=' + (90 * 24 * 60 * 60) + '; SameSite=Lax';
    }

    function getTikTokClickId() {
        return getQueryParam('ttclid') || getCookie('_ttclid') || '';
    }

    // ─── 1. PageView ───────────────────────────────────────────────────
    if (cfg.events && cfg.events.pageview) {
        sendEvent('PageView', {});
    }

    // ─── 2. ViewContent (Product Page) ─────────────────────────────────
    if (cfg.events && cfg.events.viewcontent && cfg.page_type === 'product' && cfg.product) {
        sendEvent('ViewContent', {
            content_ids: [String(cfg.product.id)],
            content_name: cfg.product.name,
            content_type: 'product',
            content_category: cfg.product.category || '',
            value: cfg.product.price,
            currency: cfg.product.currency
        });
    }

    // ─── 3. AddToCart ──────────────────────────────────────────────────
    // BUG FIX: একটাই পদ্ধতি ব্যবহার করো — jQuery `added_to_cart` থাকলে সেটা,
    // না থাকলে click listener। দুটো একসাথে চললে double-fire হয়।
    if (cfg.events && cfg.events.addtocart) {
        var addToCartFiredViaAjax = false;

        // jQuery AJAX event — most reliable (fires AFTER WooCommerce confirms add)
        if (typeof jQuery !== 'undefined') {
            jQuery(document.body).on('added_to_cart', function(e, fragments, hash, $btn) {
                addToCartFiredViaAjax = true;
                var pid = $btn ? $btn.attr('data-product_id') : '';
                var pname = $btn ? $btn.attr('data-product_name') : '';
                var pprice = $btn ? parseFloat($btn.attr('data-product_price') || 0) : 0;
                sendEvent('AddToCart', {
                    content_ids: [pid || ''],
                    content_name: pname || '',
                    content_type: 'product',
                    value: pprice,
                    currency: (cfg.product ? cfg.product.currency : 'BDT')
                });
            });
        }

        // Click fallback — শুধু তখনই চলবে যখন jQuery AJAX event চলেনি
        // (single product page with form submit, or non-AJAX themes)
        document.addEventListener('click', function(e) {
            var btn = e.target.closest('.add_to_cart_button, .single_add_to_cart_button');
            if (!btn) return;

            // AJAX-enabled বাটনে click listener দরকার নেই — jQuery event handle করবে
            if (btn.classList.contains('ajax_add_to_cart')) return;

            var productData = {};
            if (cfg.product) {
                productData = {
                    content_ids: [String(cfg.product.id)],
                    content_name: cfg.product.name,
                    content_type: 'product',
                    value: cfg.product.price,
                    currency: cfg.product.currency
                };
            } else {
                var pid = btn.getAttribute('data-product_id') || '';
                productData = {
                    content_ids: [pid],
                    content_name: btn.getAttribute('data-product_name') || '',
                    content_type: 'product',
                    value: parseFloat(btn.getAttribute('data-product_price') || 0),
                    currency: 'BDT'
                };
            }
            sendEvent('AddToCart', productData);
        });
    }

    // ─── 4. InitiateCheckout ───────────────────────────────────────────
    if (cfg.events && cfg.events.checkout && cfg.page_type === 'checkout') {
        var checkoutData = cfg.cart || {};
        sendEvent('InitiateCheckout', {
            content_ids: checkoutData.content_ids || [],
            content_type: 'product',
            value: checkoutData.value || 0,
            currency: checkoutData.currency || 'BDT',
            num_items: checkoutData.num_items || 0
        });
    }

    // ─── 5. ViewCart (WooCommerce Cart Page) ───────────────────────────
    if (cfg.events && cfg.events.viewcart && cfg.page_type === 'cart') {
        var cartData = cfg.cart || {};
        sendEvent('ViewCart', {
            content_ids: cartData.content_ids || [],
            content_type: 'product',
            value: cartData.value || 0,
            currency: cartData.currency || 'BDT',
            num_items: cartData.num_items || 0
        });
    }

    // ─── 6. RemoveFromCart ─────────────────────────────────────────────
    // BUG FIX:
    // (a) Classic cart-এ remove বাটন ক্লিক করলে পেজ reload হয়।
    //     sendBeacon() পাঠানোর আগেই navigate হতে পারে।
    //     তাই synchronous XHR দিয়ে পাঠাই।
    // (b) WooCommerce Blocks cart-এ বাটনের class আলাদা।
    // (c) jQuery `removed_from_cart` event — AJAX removal-এ এটাই reliable।
    //     দুটো method এক সাথে না চালিয়ে flag দিয়ে deduplicate করো।
    if (cfg.events && cfg.events.removefromcart) {
        var removeFiredViaJQ = false;

        // jQuery AJAX removal event (AJAX-enabled cart/Blocks)
        if (typeof jQuery !== 'undefined') {
            jQuery(document.body).on('removed_from_cart', function(e, fragments, hash, $btn) {
                removeFiredViaJQ = true;
                var pid = $btn ? $btn.attr('data-product_id') : '';
                sendEvent('RemoveFromCart', {
                    content_ids: [pid || ''],
                    content_type: 'product'
                });
            });

            // WooCommerce Blocks fires wc-blocks_removed_from_cart
            jQuery(document.body).on('wc-blocks_removed_from_cart', function() {
                removeFiredViaJQ = true;
                sendEvent('RemoveFromCart', { content_type: 'product' });
            });
        }

        // Click listener — Classic cart (non-AJAX) ব্যাকআপ
        // Selectors: WC classic = "a.remove", WC Blocks = button with aria-label containing "Remove"
        document.addEventListener('click', function(e) {
            // Selector 1: Classic WooCommerce cart remove link
            var btn = e.target.closest('a.remove[data-product_id], .remove_from_cart_button');

            // Selector 2: WooCommerce Blocks remove button
            if (!btn) {
                btn = e.target.closest('button.wc-block-cart-item__remove-link, [aria-label*="Remove"]');
            }

            if (!btn) return;

            // 50ms অপেক্ষা করো — jQuery event আগে ফায়ার হলে skip করো
            setTimeout(function() {
                if (removeFiredViaJQ) { removeFiredViaJQ = false; return; }
                var pid = btn.getAttribute('data-product_id') || '';

                // Classic cart: page navigate হবে — synchronous পাঠাও
                var isClassicRemove = btn.tagName === 'A' && btn.getAttribute('href');
                sendEvent('RemoveFromCart', {
                    content_ids: [pid],
                    content_type: 'product'
                }, isClassicRemove);
            }, 0);
        });
    }

    // ─── 7. AddPaymentInfo ─────────────────────────────────────────────
    // BUG FIX: WooCommerce Blocks checkout-এ radio input নেই।
    // Classic: input[name="payment_method"] change event
    // Blocks: MutationObserver + custom jQuery event
    if (cfg.events && cfg.events.addpaymentinfo && cfg.page_type === 'checkout') {
        var paymentFired = false;

        function fireAddPaymentInfo(method) {
            if (paymentFired) return;
            paymentFired = true;
            sendEvent('AddPaymentInfo', { payment_method: method || '' });
        }

        // Classic WooCommerce checkout — radio button change
        document.addEventListener('change', function(e) {
            if (e.target.name === 'payment_method') {
                fireAddPaymentInfo(e.target.value);
            }
        });

        // WooCommerce Blocks checkout — custom jQuery event
        if (typeof jQuery !== 'undefined') {
            jQuery(document.body).on('payment_method_selected', function() {
                var sel = document.querySelector('.wc-block-components-radio-control__input:checked');
                fireAddPaymentInfo(sel ? sel.value : '');
            });
        }

        // Blocks: observe DOM for payment method radio changes
        if (typeof MutationObserver !== 'undefined') {
            var payObserver = new MutationObserver(function() {
                var checked = document.querySelector(
                    '.wc-block-components-radio-control__input:checked, ' +
                    'input[name="radio-control-wc-payment-method-options"]:checked'
                );
                if (checked) fireAddPaymentInfo(checked.value);
            });
            var payContainer = document.querySelector('.wc-block-checkout, #payment');
            if (payContainer) {
                payObserver.observe(payContainer, { subtree: true, attributes: true, childList: true });
            }
        }
    }

    // ─── 8. Lead (Form Submissions) ────────────────────────────────────
    if (cfg.events && cfg.events.lead) {
        document.addEventListener('submit', function(e) {
            var form = e.target;
            if (form.classList.contains('woocommerce-checkout') ||
                form.classList.contains('woocommerce-cart-form') ||
                form.getAttribute('role') === 'search') return;
            if (form.id === 'loginform' || form.id === 'registerform') return;
            sendEvent('Lead', {});
        });
    }

    // ─── 9. Search ─────────────────────────────────────────────────────
    if (cfg.events && cfg.events.search && cfg.page_type === 'search' && cfg.search_string) {
        sendEvent('Search', { search_string: cfg.search_string });
    }

})();
JS;
}


// ─── AJAX Handler: Track Event (Server-Side — bypasses cache) ──────────────────
add_action( 'wp_ajax_capigw_track_event', 'capigw_ajax_track_event' );
add_action( 'wp_ajax_nopriv_capigw_track_event', 'capigw_ajax_track_event' );

function capigw_ajax_track_event() {
    // Nonce verification removed to ensure compatibility with page caching plugins (WP Rocket, LiteSpeed, etc.)
    // Instead, we validate the request origin and restrict allowed event names to prevent bot abuse.
    $nonce = isset( $_POST['nonce'] ) ? sanitize_text_field( wp_unslash( $_POST['nonce'] ) ) : '';

    // ─── Origin Validation (replaces nonce for cache-safe security) ─────
    $allowed_host = parse_url( home_url(), PHP_URL_HOST );
    if ( ! $allowed_host ) {
        $allowed_host = $_SERVER['HTTP_HOST'] ?? '';
    }

    $request_origin = isset( $_SERVER['HTTP_ORIGIN'] ) ? $_SERVER['HTTP_ORIGIN'] : '';
    $request_referer = isset( $_SERVER['HTTP_REFERER'] ) ? $_SERVER['HTTP_REFERER'] : '';

    $origin_valid = false;
    
    // Check Origin
    if ( ! empty( $request_origin ) ) {
        $origin_host = parse_url( $request_origin, PHP_URL_HOST );
        if ( capigw_host_allowed( $origin_host, $allowed_host ) ) {
            $origin_valid = true;
        }
    }
    
    // Check Referer if Origin is missing or invalid
    if ( ! $origin_valid && ! empty( $request_referer ) ) {
        $referer_host = parse_url( $request_referer, PHP_URL_HOST );
        if ( capigw_host_allowed( $referer_host, $allowed_host ) ) {
            $origin_valid = true;
        }
    }

    if ( ! $origin_valid ) {
        wp_send_json_error( 'Invalid origin' );
    }

    if ( capigw_ajax_rate_limited() ) {
        wp_send_json_error( 'Rate limit exceeded', 429 );
    }

    // ─── Whitelist allowed event names ──────────────────────────────────
    $allowed_events = array( 'PageView', 'ViewContent', 'AddToCart', 'ViewCart', 'RemoveFromCart', 'InitiateCheckout', 'AddPaymentInfo', 'Purchase', 'Lead', 'Search' );

    // Also allow user-defined custom events from the Custom Event Builder
    if ( defined( 'CAPIGW_CUSTOM_EVENTS_KEY' ) ) {
        $custom_events = get_option( CAPIGW_CUSTOM_EVENTS_KEY, array() );
        foreach ( $custom_events as $ce ) {
            if ( ! empty( $ce['name'] ) && ! empty( $ce['enabled'] ) ) {
                $allowed_events[] = $ce['name'];
            }
        }
    }

    $settings   = capigw_get_settings();
    $event_name = isset( $_POST['event_name'] ) ? sanitize_text_field( wp_unslash( $_POST['event_name'] ) ) : '';
    $event_json = isset( $_POST['event_data'] ) ? wp_unslash( $_POST['event_data'] ) : '{}';
    $page_url   = isset( $_POST['page_url'] ) ? esc_url_raw( wp_unslash( $_POST['page_url'] ) ) : '';
    $fbp        = isset( $_POST['fbp'] ) ? sanitize_text_field( wp_unslash( $_POST['fbp'] ) ) : '';
    $fbc        = isset( $_POST['fbc'] ) ? sanitize_text_field( wp_unslash( $_POST['fbc'] ) ) : '';
    $ttp        = isset( $_POST['ttp'] ) ? sanitize_text_field( wp_unslash( $_POST['ttp'] ) ) : '';
    $ttclid     = isset( $_POST['ttclid'] ) ? sanitize_text_field( wp_unslash( $_POST['ttclid'] ) ) : '';

    if ( empty( $event_name ) || ! in_array( $event_name, $allowed_events, true ) ) {
        wp_send_json_error( 'Invalid event name' );
    }

    $custom_data = json_decode( $event_json, true );
    if ( ! is_array( $custom_data ) ) {
        $custom_data = array();
    }

    // Build user_data with PII hashing
    $user_data = array(
        'client_ip_address' => capigw_get_real_ip(),
        'client_user_agent' => sanitize_text_field( $_SERVER['HTTP_USER_AGENT'] ?? '' ),
    );

    // Add fbp/fbc cookies for Facebook matching
    if ( ! empty( $fbp ) ) {
        $user_data['fbp'] = $fbp;
    }
    if ( ! empty( $fbc ) ) {
        $user_data['fbc'] = $fbc;
    }
    if ( ! empty( $ttp ) ) {
        $user_data['ttp'] = $ttp;
    }
    if ( ! empty( $ttclid ) ) {
        $user_data['ttclid'] = $ttclid;
    }

    // If user is logged in, hash their email and name
    if ( is_user_logged_in() ) {
        $user = wp_get_current_user();
        if ( $user->user_email ) {
            $user_data['em'] = array( capigw_hash( $user->user_email ) );
        }
        if ( $user->first_name ) {
            $user_data['fn'] = array( capigw_hash( $user->first_name ) );
        }
        if ( $user->last_name ) {
            $user_data['ln'] = array( capigw_hash( $user->last_name ) );
        }
    }

    // Build event payload
    $event_payload = array(
        'event_name'  => $event_name,
        'event_time'  => time(),
        'event_source_url' => $page_url,
        'action_source'    => 'website',
        'user_data'   => $user_data,
    );

    // Add custom_data if present
    if ( ! empty( $custom_data ) ) {
        $event_payload['custom_data'] = $custom_data;
    }

    // Generate unique event_id for deduplication
    $event_payload['event_id'] = 'wp_' . $event_name . '_' . time() . '_' . wp_rand( 1000, 9999 );

    // Send to gateway
    capigw_send_event( $event_payload, false );

    wp_send_json_success( 'Event tracked' );
}


// ─── Helper: Lightweight AJAX Rate Limit ───────────────────────────────────
function capigw_ajax_rate_limited() {
    $ip = capigw_get_real_ip();
    if ( empty( $ip ) ) {
        return false;
    }

    $limit      = 120;
    $window     = 60;
    $cache_key  = 'capigw_ajax_rate_' . md5( $ip );
    $hit_count  = (int) get_transient( $cache_key );

    if ( $hit_count >= $limit ) {
        return true;
    }

    set_transient( $cache_key, $hit_count + 1, $window );
    return false;
}


// ─── WooCommerce: Purchase Event on Thank You Page (Server-Side) ───────────────
add_action( 'woocommerce_thankyou', 'capigw_track_purchase', 10, 1 );

function capigw_track_purchase( $order_id ) {
    $settings = capigw_get_settings();

    if ( ! $settings['enable_purchase'] || empty( $settings['api_key'] ) ) {
        return;
    }

    // Prevent duplicate tracking (mark order as tracked)
    $already_tracked = capigw_get_order_meta( $order_id, '_capigw_tracked' );
    if ( $already_tracked ) {
        return;
    }

    $order = wc_get_order( $order_id );
    if ( ! $order ) {
        return;
    }

    // Build product IDs and content data
    $content_ids = array();
    $contents    = array();
    $num_items   = 0;

    foreach ( $order->get_items() as $item ) {
        $product_id = $item->get_product_id();
        $content_ids[] = (string) $product_id;
        $contents[] = array(
            'id'       => (string) $product_id,
            'quantity' => $item->get_quantity(),
            'item_price' => (float) ( $item->get_total() / max( $item->get_quantity(), 1 ) ),
        );
        $num_items += $item->get_quantity();
    }

    // Build user_data with real customer info (hashed)
    $user_data = array(
        'client_ip_address' => $order->get_customer_ip_address() ?: capigw_get_real_ip(),
        'client_user_agent' => $order->get_customer_user_agent() ?: ( $_SERVER['HTTP_USER_AGENT'] ?? '' ),
    );

    if ( $order->get_billing_email() ) {
        $user_data['em'] = array( capigw_hash( $order->get_billing_email() ) );
    }
    if ( $order->get_billing_first_name() ) {
        $user_data['fn'] = array( capigw_hash( $order->get_billing_first_name() ) );
    }
    if ( $order->get_billing_last_name() ) {
        $user_data['ln'] = array( capigw_hash( $order->get_billing_last_name() ) );
    }
    if ( $order->get_billing_phone() ) {
        $user_data['ph'] = array( capigw_hash_phone( $order->get_billing_phone() ) );
    }
    if ( $order->get_billing_city() ) {
        $user_data['ct'] = array( capigw_hash( $order->get_billing_city() ) );
    }
    if ( $order->get_billing_state() ) {
        $user_data['st'] = array( capigw_hash( $order->get_billing_state() ) );
    }
    if ( $order->get_billing_country() ) {
        $user_data['country'] = array( capigw_hash( $order->get_billing_country() ) );
    }
    if ( $order->get_billing_postcode() ) {
        $user_data['zp'] = array( capigw_hash( $order->get_billing_postcode() ) );
    }

    // Add fbp/fbc from cookies
    if ( isset( $_COOKIE['_fbp'] ) ) {
        $user_data['fbp'] = sanitize_text_field( wp_unslash( $_COOKIE['_fbp'] ) );
    }
    if ( isset( $_COOKIE['_fbc'] ) ) {
        $user_data['fbc'] = sanitize_text_field( wp_unslash( $_COOKIE['_fbc'] ) );
    }
    if ( isset( $_COOKIE['_ttp'] ) ) {
        $user_data['ttp'] = sanitize_text_field( wp_unslash( $_COOKIE['_ttp'] ) );
    }
    if ( isset( $_COOKIE['_ttclid'] ) ) {
        $user_data['ttclid'] = sanitize_text_field( wp_unslash( $_COOKIE['_ttclid'] ) );
    }

    // Build event payload
    $event_payload = array(
        'event_name'       => 'Purchase',
        'event_time'       => time(),
        'event_id'         => 'wc_purchase_' . $order_id,
        'event_source_url' => $order->get_checkout_order_received_url(),
        'action_source'    => 'website',
        'user_data'        => $user_data,
        'custom_data'      => array(
            'value'        => (float) $order->get_total(),
            'currency'     => $order->get_currency(),
            'content_ids'  => $content_ids,
            'contents'     => $contents,
            'content_type' => 'product',
            'num_items'    => $num_items,
            'order_id'     => (string) $order_id,
        ),
    );

    $sent = false;

    // If deferred_purchase is ON, send with hold=true query param
    if ( $settings['deferred_purchase'] ) {
        $url = rtrim( $settings['gateway_url'], '/' ) . '/events?hold=true';
        $body = wp_json_encode( array( 'data' => array( $event_payload ) ) );
        $headers = array_merge( array(
            'Content-Type' => 'application/json',
            'X-API-Key'    => $settings['api_key'],
        ), capigw_signed_headers( $settings['api_key'], $body ) );

        $response = wp_remote_post( $url, array(
            'timeout'   => 10,
            'sslverify' => true,
            'headers'   => $headers,
            'body'      => $body,
        ) );

        if ( is_wp_error( $response ) ) {
            // Critical failure — always log regardless of debug_mode
            error_log( '[CAPI Gateway] Deferred purchase send failed for order #' . $order_id . ': ' . $response->get_error_message() );
        }

        if ( ! is_wp_error( $response ) ) {
            $code = wp_remote_retrieve_response_code( $response );
            $sent = ( $code >= 200 && $code < 300 );
            if ( ! $sent && $settings['debug_mode'] ) {
                error_log( '[CAPI Gateway] Deferred purchase HTTP ' . $code . ': ' . wp_remote_retrieve_body( $response ) );
            }
        }
    } else {
        // Immediate send
        $sent = capigw_send_event( $event_payload, true );
    }

    // Mark as tracked to prevent duplicates
    if ( ! $sent ) {
        capigw_update_order_meta( $order_id, '_capigw_confirm_status', 'send_failed' );
        return;
    }

    capigw_update_order_meta( $order_id, '_capigw_tracked', 1 );

    if ( $settings['debug_mode'] ) {
        error_log( '[CAPI Gateway] Purchase tracked for order #' . $order_id );
    }
}


// ─── Helper: Get Real Client IP ────────────────────────────────────────────────
function capigw_get_real_ip() {
    $headers = array(
        'HTTP_CF_CONNECTING_IP',   // Cloudflare
        'HTTP_X_FORWARDED_FOR',    // Proxies
        'HTTP_X_REAL_IP',          // Nginx
        'REMOTE_ADDR',             // Default
    );

    foreach ( $headers as $header ) {
        if ( ! empty( $_SERVER[ $header ] ) ) {
            $ip = $_SERVER[ $header ];
            // X-Forwarded-For can have multiple IPs, take the first
            if ( strpos( $ip, ',' ) !== false ) {
                $ip = trim( explode( ',', $ip )[0] );
            }
            if ( filter_var( $ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE ) ) {
                return $ip;
            }
        }
    }

    return $_SERVER['REMOTE_ADDR'] ?? '';
}
