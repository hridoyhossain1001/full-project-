<?php
/**
 * CAPI Gateway — Admin Settings Page
 *
 * WordPress Admin প্যানেলে সুন্দর সেটিংস পেজ তৈরি করে।
 * ক্লায়েন্ট শুধু API Key বসাবে, বাকি সব অটোমেটিক।
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// ─── Register Admin Menu ───────────────────────────────────────────────────────
add_action( 'admin_menu', 'capigw_admin_menu' );

function capigw_admin_menu() {
    add_menu_page(
        'CAPI Gateway Settings',       // Page title
        'CAPI Gateway',                // Menu title
        'manage_options',              // Capability
        'capi-gateway',                // Menu slug
        'capigw_settings_page',        // Callback function
        'dashicons-chart-area',        // Icon
        58                             // Position
    );
}

// ─── Register Settings ─────────────────────────────────────────────────────────
add_action( 'admin_init', 'capigw_register_settings' );

function capigw_register_settings() {
    register_setting( 'capigw_settings_group', CAPIGW_OPTION_KEY, 'capigw_sanitize_settings' );
}

// ─── Admin Notice: Cache Cleared After Save ────────────────────────────────────
add_action( 'admin_notices', 'capigw_maybe_show_cache_notice' );

function capigw_maybe_show_cache_notice() {
    $screen = get_current_screen();
    if ( ! $screen || $screen->id !== 'toplevel_page_capi-gateway' ) {
        return;
    }

    // Only show after a settings save (settings-updated query param)
    if ( ! isset( $_GET['settings-updated'] ) || $_GET['settings-updated'] !== 'true' ) {
        return;
    }
    ?>
    <div class="notice notice-success is-dismissible" style="border-left-color:#4f46e5;">
        <p>
            <strong>⚡ CAPI Gateway:</strong>
            সেটিংস সেভ হয়েছে এবং ওয়েবসাইটের পেজ ক্যাশ <strong>স্বয়ংক্রিয়ভাবে ক্লিয়ার</strong> করা হয়েছে।
            আপনি যদি Cloudflare বা অন্য কোনো CDN ব্যবহার করেন, তাহলে সেখান থেকেও ম্যানুয়ালি ক্যাশ ক্লিয়ার করুন।
        </p>
    </div>
    <?php
}

function capigw_sanitize_settings( $input ) {
    $sanitized = array();
    $sanitized['api_key']            = sanitize_text_field( $input['api_key'] ?? '' );
    $sanitized['gateway_url']        = esc_url_raw( $input['gateway_url'] ?? CAPIGW_DEFAULT_GATEWAY_URL );
    // Core Events
    $sanitized['enable_pageview']       = isset( $input['enable_pageview'] ) ? 1 : 0;
    $sanitized['enable_lead']           = isset( $input['enable_lead'] ) ? 1 : 0;
    $sanitized['enable_search']         = isset( $input['enable_search'] ) ? 1 : 0;
    // WooCommerce Events
    $sanitized['enable_viewcontent']    = isset( $input['enable_viewcontent'] ) ? 1 : 0;
    $sanitized['enable_addtocart']      = isset( $input['enable_addtocart'] ) ? 1 : 0;
    $sanitized['enable_viewcart']       = isset( $input['enable_viewcart'] ) ? 1 : 0;
    $sanitized['enable_removefromcart'] = isset( $input['enable_removefromcart'] ) ? 1 : 0;
    $sanitized['enable_checkout']       = isset( $input['enable_checkout'] ) ? 1 : 0;
    $sanitized['enable_addpaymentinfo'] = isset( $input['enable_addpaymentinfo'] ) ? 1 : 0;
    $sanitized['enable_purchase']       = isset( $input['enable_purchase'] ) ? 1 : 0;
    $sanitized['deferred_purchase']  = isset( $input['deferred_purchase'] ) ? 1 : 0;
    $sanitized['auto_confirm_status']= sanitize_text_field( $input['auto_confirm_status'] ?? 'completed' );
    $sanitized['debug_mode']         = isset( $input['debug_mode'] ) ? 1 : 0;
    return $sanitized;
}

// ─── AJAX: Connection Test ─────────────────────────────────────────────────────
add_action( 'wp_ajax_capigw_test_connection', 'capigw_test_connection' );

function capigw_test_connection() {
    check_ajax_referer( 'capigw_nonce', 'nonce' );

    if ( ! current_user_can( 'manage_options' ) ) {
        wp_send_json_error( 'Permission denied' );
    }

    $api_key     = sanitize_text_field( $_POST['api_key'] ?? '' );
    $gateway_url = esc_url_raw( $_POST['gateway_url'] ?? '' );

    if ( empty( $api_key ) || empty( $gateway_url ) ) {
        wp_send_json_error( 'API Key এবং Gateway URL দিন।' );
    }

    // Send a test ping to the gateway health endpoint
    $url = rtrim( $gateway_url, '/' ) . '/health';

    $response = wp_remote_get( $url, array(
        'timeout'   => 30,
        'sslverify' => true,
        'headers'   => array(
            'X-API-Key' => $api_key,
        ),
    ) );

    if ( is_wp_error( $response ) ) {
        wp_send_json_error( 'Connection failed: ' . $response->get_error_message() );
    }

    $code = wp_remote_retrieve_response_code( $response );
    $body = wp_remote_retrieve_body( $response );

    if ( $code === 200 ) {
        wp_send_json_success( 'Connected successfully! Server is online.' );
    } else {
        wp_send_json_error( "Server responded with HTTP $code. Response: $body" );
    }
}

// ─── Settings Page HTML ────────────────────────────────────────────────────────
function capigw_settings_page() {
    $settings = capigw_get_settings();
    $nonce    = wp_create_nonce( 'capigw_nonce' );
    ?>
    <style>
        .capigw-wrap { max-width: 860px; margin: 20px 20px 32px 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1d2327; }
        .capigw-header { background: #fff; color: #1d2327; padding: 24px; border: 1px solid #dcdcde; border-left: 4px solid #4f46e5; border-radius: 4px; margin-bottom: 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
        .capigw-header h1 { margin: 0 0 6px; font-size: 24px; font-weight: 700; line-height: 1.25; }
        .capigw-header p { margin: 0; color: #50575e; font-size: 14px; }
        .capigw-header .version { background: #eef2ff; color: #3730a3; padding: 3px 9px; border-radius: 999px; font-size: 12px; margin-left: 8px; vertical-align: middle; }
        /* Tab Navigation */
        .capigw-nav-tabs { display: flex; gap: 0; border-bottom: 2px solid #dcdcde; margin-bottom: 20px; }
        .capigw-nav-tab { padding: 12px 22px; font-size: 14px; font-weight: 600; color: #50575e; cursor: pointer; border: 1px solid transparent; border-bottom: none; border-radius: 4px 4px 0 0; background: transparent; transition: all 0.2s; position: relative; bottom: -2px; }
        .capigw-nav-tab:hover { color: #1d2327; background: #f6f7f7; }
        .capigw-nav-tab.active { color: #4f46e5; background: #fff; border-color: #dcdcde; border-bottom: 2px solid #fff; }
        .capigw-tab-content { display: none; }
        .capigw-tab-content.active { display: block; }
        /* Cards & Fields */
        .capigw-card { background: #fff; border: 1px solid #dcdcde; border-radius: 4px; padding: 22px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(0,0,0,0.035); }
        .capigw-card h2 { margin: 0 0 16px; font-size: 17px; color: #1d2327; border-bottom: 1px solid #dcdcde; padding-bottom: 10px; display: block; }
        .capigw-card > p { color: #50575e !important; line-height: 1.55; }
        .capigw-field { margin-bottom: 18px; }
        .capigw-field label { display: block; font-weight: 600; margin-bottom: 6px; color: #1d2327; font-size: 14px; }
        .capigw-field input[type="text"],
        .capigw-field input[type="password"],
        .capigw-field select { width: 100%; max-width: 100%; min-height: 40px; padding: 8px 12px; border: 1px solid #8c8f94; border-radius: 4px; font-size: 14px; transition: border-color 0.15s, box-shadow 0.15s; }
        .capigw-field input:focus, .capigw-field select:focus { border-color: #4f46e5; outline: none; box-shadow: 0 0 0 2px rgba(79,70,229,0.18); }
        .capigw-field .description { font-size: 13px; color: #50575e; margin-top: 6px; line-height: 1.45; }
        .capigw-toggle { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding: 10px 12px; border: 1px solid #edf0f2; border-radius: 4px; background: #fbfbfc; }
        .capigw-toggle label { font-weight: 500; color: #1d2327; margin: 0; cursor: pointer; }
        .capigw-switch { position: relative; width: 44px; height: 24px; flex-shrink: 0; }
        .capigw-switch input { opacity: 0; width: 0; height: 0; }
        .capigw-slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background: #a7aaad; border-radius: 24px; transition: 0.2s; }
        .capigw-slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background: #fff; border-radius: 50%; transition: 0.2s; box-shadow: 0 1px 2px rgba(0,0,0,0.22); }
        .capigw-switch input:checked + .capigw-slider { background: #4f46e5; }
        .capigw-switch input:checked + .capigw-slider:before { transform: translateX(20px); }
        .capigw-btn { min-height: 40px; padding: 9px 18px; border: 1px solid transparent; border-radius: 4px; font-size: 14px; font-weight: 600; cursor: pointer; transition: background 0.15s, border-color 0.15s; }
        .capigw-btn-primary { background: #4f46e5; color: #fff; border-color: #4338ca; }
        .capigw-btn-primary:hover { background: #4338ca; color: #fff; }
        .capigw-btn-test { background: #1d2327; color: #fff; margin-right: 10px; }
        .capigw-btn-test:hover { background: #2c3338; color: #fff; }
        .capigw-status { padding: 12px 14px; border-radius: 4px; margin-top: 12px; display: none; font-size: 13px; line-height: 1.45; }
        .capigw-status.success { display: block; background: #ecfdf3; color: #166534; border: 1px solid #bbf7d0; }
        .capigw-status.error { display: block; background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .capigw-events-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
        .capigw-info-box { background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 4px; padding: 14px 16px; font-size: 13px; color: #3730a3; line-height: 1.55; margin-bottom: 16px; }
        @media (max-width: 782px) {
            .capigw-wrap { margin-right: 12px; }
            .capigw-header, .capigw-card { padding: 18px; }
            .capigw-events-grid { grid-template-columns: 1fr; }
            .capigw-btn { width: 100%; margin: 0 0 10px; text-align: center; }
            .capigw-nav-tabs { flex-wrap: wrap; }
            .capigw-nav-tab { flex: 1; text-align: center; font-size: 13px; padding: 10px 12px; }
        }
    </style>

    <div class="capigw-wrap">
        <!-- Header -->
        <div class="capigw-header">
            <h1>⚡ CAPI Gateway <span class="version">v<?php echo CAPIGW_VERSION; ?></span></h1>
            <p>Server-Side Facebook CAPI, TikTok & GA4 Tracking for WooCommerce</p>
        </div>

        <form method="post" action="options.php" id="capigw-form">
            <?php settings_fields( 'capigw_settings_group' ); ?>

            <!-- Tab Navigation -->
            <div class="capigw-nav-tabs">
                <div class="capigw-nav-tab active" data-tab="general">⚙️ General</div>
                <div class="capigw-nav-tab" data-tab="woocommerce">🛒 WooCommerce</div>
                <div class="capigw-nav-tab" data-tab="advanced">🛠️ Advanced</div>
            </div>

            <!-- ═══════════════════════════════════════════════════════════════ -->
            <!-- TAB 1: General Settings                                        -->
            <!-- ═══════════════════════════════════════════════════════════════ -->
            <div class="capigw-tab-content active" id="tab-general">

                <!-- Connection Settings -->
                <div class="capigw-card">
                    <h2>🔑 Connection Settings</h2>

                    <div class="capigw-field">
                        <label for="capigw_api_key">API Key</label>
                        <input type="password" id="capigw_api_key"
                               name="<?php echo CAPIGW_OPTION_KEY; ?>[api_key]"
                               value="<?php echo esc_attr( $settings['api_key'] ); ?>"
                               placeholder="আপনার CAPI Gateway API Key পেস্ট করুন"
                               autocomplete="off">
                        <p class="description">CAPI Gateway ড্যাশবোর্ড থেকে আপনার API Key কপি করুন।</p>
                    </div>

                    <div class="capigw-field">
                        <label for="capigw_gateway_url">Gateway URL</label>
                        <input type="text" id="capigw_gateway_url"
                               name="<?php echo CAPIGW_OPTION_KEY; ?>[gateway_url]"
                               value="<?php echo esc_attr( $settings['gateway_url'] ); ?>"
                               placeholder="https://your-gateway.herokuapp.com/api/v1">
                        <p class="description">সাধারণত এটি পরিবর্তন করার দরকার হয় না।</p>
                    </div>

                    <button type="button" class="capigw-btn capigw-btn-test" id="capigw-test-btn" onclick="capigwTestConnection()">
                        🔍 Test Connection
                    </button>
                    <div id="capigw-test-status" class="capigw-status"></div>
                </div>

                <!-- Core Events -->
                <div class="capigw-card">
                    <h2>📊 Core Events</h2>
                    <p style="color:#666; font-size:13px; margin-bottom:16px;">সকল ধরনের ওয়েবসাইটের জন্য — ব্লগ, কর্পোরেট সাইট, ল্যান্ডিং পেজ, ই-কমার্স সবখানে কাজ করবে:</p>

                    <div class="capigw-events-grid">
                        <?php
                        $core_events = array(
                            'enable_pageview' => array( '👁️ PageView', 'প্রতিটি পেজ ভিজিট ট্র্যাক করে' ),
                            'enable_lead'     => array( '📋 Lead', 'ফর্ম সাবমিশন ও সাইনআপ ট্র্যাক করে' ),
                            'enable_search'   => array( '🔍 Search', 'সাইটে সার্চ করা ট্র্যাক করে' ),
                        );
                        foreach ( $core_events as $key => $info ) :
                        ?>
                            <div class="capigw-toggle">
                                <label class="capigw-switch">
                                    <input type="checkbox"
                                           name="<?php echo CAPIGW_OPTION_KEY; ?>[<?php echo $key; ?>]"
                                           value="1"
                                           <?php checked( $settings[ $key ], 1 ); ?>>
                                    <span class="capigw-slider"></span>
                                </label>
                                <label><?php echo $info[0]; ?> <span style="color:#888; font-size:12px;">— <?php echo $info[1]; ?></span></label>
                            </div>
                        <?php endforeach; ?>
                    </div>
                </div>

            </div><!-- /tab-general -->


            <!-- ═══════════════════════════════════════════════════════════════ -->
            <!-- TAB 2: WooCommerce Events                                      -->
            <!-- ═══════════════════════════════════════════════════════════════ -->
            <div class="capigw-tab-content" id="tab-woocommerce">

                <!-- WooCommerce Tracking Events -->
                <div class="capigw-card">
                    <h2>🛒 WooCommerce Event Tracking</h2>
                    <p style="color:#666; font-size:13px; margin-bottom:16px;">ই-কমার্স ওয়েবসাইটের জন্য — WooCommerce ইভেন্টগুলো এখান থেকে চালু/বন্ধ করুন:</p>

                    <div class="capigw-events-grid">
                        <?php
                        $woo_events = array(
                            'enable_viewcontent'    => array( '📦 ViewContent', 'প্রোডাক্ট পেজ ভিউ ট্র্যাক করে' ),
                            'enable_addtocart'      => array( '🛒 AddToCart', 'কার্টে প্রোডাক্ট যোগ করা ট্র্যাক করে' ),
                            'enable_viewcart'       => array( '👀 ViewCart', 'কার্ট পেজ ভিজিট ট্র্যাক করে' ),
                            'enable_removefromcart'  => array( '❌ RemoveFromCart', 'কার্ট থেকে প্রোডাক্ট বাদ দেওয়া ট্র্যাক করে' ),
                            'enable_checkout'       => array( '💳 InitiateCheckout', 'চেকআউট শুরু করা ট্র্যাক করে' ),
                            'enable_addpaymentinfo' => array( '🏦 AddPaymentInfo', 'পেমেন্ট ইনফো দেওয়া ট্র্যাক করে' ),
                            'enable_purchase'       => array( '💰 Purchase', 'অর্ডার সম্পন্ন হওয়া ট্র্যাক করে' ),
                        );
                        foreach ( $woo_events as $key => $info ) :
                        ?>
                            <div class="capigw-toggle">
                                <label class="capigw-switch">
                                    <input type="checkbox"
                                           name="<?php echo CAPIGW_OPTION_KEY; ?>[<?php echo $key; ?>]"
                                           value="1"
                                           <?php checked( $settings[ $key ], 1 ); ?>>
                                    <span class="capigw-slider"></span>
                                </label>
                                <label><?php echo $info[0]; ?> <span style="color:#888; font-size:12px;">— <?php echo $info[1]; ?></span></label>
                            </div>
                        <?php endforeach; ?>
                    </div>
                </div>

                <!-- Deferred Purchase (COD) -->
                <div class="capigw-card">
                    <h2>📦 Deferred Purchase (COD Support)</h2>
                    <p style="color:#666; font-size:13px; margin-bottom:16px;">
                        ক্যাশ-অন-ডেলিভারি (COD) অর্ডারের জন্য Purchase ইভেন্ট তখনই Facebook-এ পাঠানো হবে যখন অর্ডারের স্ট্যাটাস পরিবর্তন হবে।
                    </p>

                    <div class="capigw-toggle">
                        <label class="capigw-switch">
                            <input type="checkbox"
                                   name="<?php echo CAPIGW_OPTION_KEY; ?>[deferred_purchase]"
                                   value="1"
                                   <?php checked( $settings['deferred_purchase'], 1 ); ?>>
                            <span class="capigw-slider"></span>
                        </label>
                        <label>Deferred Purchase চালু করুন</label>
                    </div>

                    <div class="capigw-field">
                        <label for="capigw_auto_confirm">অটো-কনফার্ম স্ট্যাটাস</label>
                        <select id="capigw_auto_confirm"
                                name="<?php echo CAPIGW_OPTION_KEY; ?>[auto_confirm_status]">
                            <option value="processing" <?php selected( $settings['auto_confirm_status'], 'processing' ); ?>>Processing</option>
                            <option value="completed" <?php selected( $settings['auto_confirm_status'], 'completed' ); ?>>Completed</option>
                        </select>
                        <p class="description">এই স্ট্যাটাসে অর্ডার গেলে Purchase event অটোমেটিক Facebook-এ যাবে।</p>
                    </div>
                </div>

            </div><!-- /tab-woocommerce -->


            <!-- ═══════════════════════════════════════════════════════════════ -->
            <!-- TAB 3: Advanced                                                -->
            <!-- ═══════════════════════════════════════════════════════════════ -->
            <div class="capigw-tab-content" id="tab-advanced">

                <div class="capigw-card">
                    <h2>🛠️ Debug & Logging</h2>
                    <div class="capigw-toggle">
                        <label class="capigw-switch">
                            <input type="checkbox"
                                   name="<?php echo CAPIGW_OPTION_KEY; ?>[debug_mode]"
                                   value="1"
                                   <?php checked( $settings['debug_mode'], 1 ); ?>>
                            <span class="capigw-slider"></span>
                        </label>
                        <label>🐛 Debug Mode (error_log-এ লগ লিখবে)</label>
                    </div>
                </div>

                <div class="capigw-card">
                    <h2>🎯 Custom Event Builder</h2>
                    <div class="capigw-info-box">
                        💡 নির্দিষ্ট বাটন ক্লিক, ফর্ম সাবমিশন, বা URL ম্যাচের মাধ্যমে কাস্টম ইভেন্ট তৈরি করতে চান?
                        <br>বাম পাশের মেনু থেকে <strong>CAPI Gateway → 🎯 Custom Events</strong> এ যান।
                    </div>
                </div>

            </div><!-- /tab-advanced -->

            <!-- Save (visible on all tabs) -->
            <p>
                <?php submit_button( '💾 Save Settings', 'capigw-btn capigw-btn-primary', 'submit', false ); ?>
            </p>
        </form>
    </div>

    <script>
    // ─── Tab Switching Logic ───────────────────────────────────────────────────
    (function() {
        var tabs = document.querySelectorAll('.capigw-nav-tab');
        var panels = document.querySelectorAll('.capigw-tab-content');
        var STORAGE_KEY = 'capigw_active_tab';

        function switchTab(tabName) {
            tabs.forEach(function(t) { t.classList.remove('active'); });
            panels.forEach(function(p) { p.classList.remove('active'); });
            var activeTab = document.querySelector('.capigw-nav-tab[data-tab="' + tabName + '"]');
            var activePanel = document.getElementById('tab-' + tabName);
            if (activeTab) activeTab.classList.add('active');
            if (activePanel) activePanel.classList.add('active');
            try { localStorage.setItem(STORAGE_KEY, tabName); } catch(e) {}
        }

        tabs.forEach(function(tab) {
            tab.addEventListener('click', function() {
                switchTab(this.getAttribute('data-tab'));
            });
        });

        // Restore last active tab after page reload / save
        try {
            var saved = localStorage.getItem(STORAGE_KEY);
            if (saved && document.getElementById('tab-' + saved)) {
                switchTab(saved);
            }
        } catch(e) {}
    })();

    // ─── Test Connection ───────────────────────────────────────────────────────
    function capigwTestConnection() {
        try {
            var btn = document.getElementById('capigw-test-btn');
            var status = document.getElementById('capigw-test-status');
            var apiKey = document.getElementById('capigw_api_key').value.trim();
            var gatewayUrl = document.getElementById('capigw_gateway_url').value.trim();

            btn.disabled = true;
            btn.textContent = '⏳ Testing...';
            status.style.display = 'none';
            status.className = 'capigw-status';

            if (!apiKey || !gatewayUrl) {
                status.style.display = 'block';
                status.className = 'capigw-status error';
                status.textContent = '❌ দয়া করে API Key এবং Gateway URL দিন।';
                btn.disabled = false;
                btn.textContent = '🔍 Test Connection';
                return;
            }

            var formData = new FormData();
            formData.append('action', 'capigw_test_connection');
            formData.append('nonce', '<?php echo $nonce; ?>');
            formData.append('api_key', apiKey);
            formData.append('gateway_url', gatewayUrl);

            var ajax_url = (typeof ajaxurl !== 'undefined') ? ajaxurl : '/wp-admin/admin-ajax.php';

            fetch(ajax_url, {
                method: 'POST',
                body: formData,
            })
            .then(function(res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function(data) {
                status.style.display = 'block';
                if (data.success) {
                    status.className = 'capigw-status success';
                    status.innerHTML = '✅ ' + data.data;
                } else {
                    status.className = 'capigw-status error';
                    status.innerHTML = '❌ ' + (data.data || 'Unknown error');
                }
                btn.disabled = false;
                btn.textContent = '🔍 Test Connection';
            })
            .catch(function(err) {
                status.style.display = 'block';
                status.className = 'capigw-status error';
                status.textContent = '❌ Network error: ' + err.message;
                btn.disabled = false;
                btn.textContent = '🔍 Test Connection';
            });
        } catch (e) {
            console.error(e);
            alert("Error: " + e.message);
        }
    }
    </script>
    <?php
}
