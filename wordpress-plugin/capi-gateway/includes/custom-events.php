<?php
/**
 * CAPI Gateway — Custom Event Builder
 *
 * ক্লায়েন্ট WordPress Admin থেকে নিজের কাস্টম ইভেন্ট তৈরি করতে পারবে।
 * উদাহরণ: "WishlistAdd", "CouponUsed", "VideoWatch" ইত্যাদি।
 *
 * প্রতিটি কাস্টম ইভেন্টের জন্য সেট করা যায়:
 * - Event Name (যেমন: WishlistAdd)
 * - Trigger Type: CSS Selector Click, Page URL Match, বা Form Submit
 * - CSS Selector (যেমন: .wishlist-btn, #coupon-apply)
 * - URL Pattern (যেমন: /thank-you/, /contact-success/)
 * - Custom Data Fields (value, currency, etc.)
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// ─── Custom Events Option Key ──────────────────────────────────────────────────
define( 'CAPIGW_CUSTOM_EVENTS_KEY', 'capigw_custom_events' );

// ─── Register Admin Sub-Page ───────────────────────────────────────────────────
add_action( 'admin_menu', 'capigw_custom_events_menu' );

function capigw_custom_events_menu() {
    add_submenu_page(
        'capi-gateway',                    // Parent slug
        'Custom Event Builder',            // Page title
        '🎯 Custom Events',               // Menu title
        'manage_options',                  // Capability
        'capigw-custom-events',            // Menu slug
        'capigw_custom_events_page'        // Callback
    );
}

// ─── Save Custom Events via AJAX ───────────────────────────────────────────────
add_action( 'wp_ajax_capigw_save_custom_events', 'capigw_save_custom_events' );

function capigw_save_custom_events() {
    check_ajax_referer( 'capigw_custom_events_nonce', 'nonce' );

    if ( ! current_user_can( 'manage_options' ) ) {
        wp_send_json_error( 'Permission denied' );
    }

    $raw = $_POST['events'] ?? '[]';
    $events = json_decode( wp_unslash( $raw ), true );

    if ( ! is_array( $events ) ) {
        wp_send_json_error( 'Invalid data' );
    }

    // Sanitize each event
    $sanitized = array();
    foreach ( $events as $event ) {
        $sanitized[] = array(
            'name'         => preg_replace( '/[^A-Za-z0-9_]/', '', sanitize_text_field( $event['name'] ?? '' ) ),
            'trigger'      => sanitize_text_field( $event['trigger'] ?? 'click' ),
            'selector'     => sanitize_text_field( $event['selector'] ?? '' ),
            'url_pattern'  => sanitize_text_field( $event['url_pattern'] ?? '' ),
            'value'        => floatval( $event['value'] ?? 0 ),
            'currency'     => sanitize_text_field( $event['currency'] ?? '' ),
            'custom_param' => sanitize_text_field( $event['custom_param'] ?? '' ),
            'enabled'      => (bool) ( $event['enabled'] ?? true ),
        );
    }

    update_option( CAPIGW_CUSTOM_EVENTS_KEY, $sanitized );
    wp_send_json_success( 'Events saved!' );
}

// ─── Settings Page ─────────────────────────────────────────────────────────────
function capigw_custom_events_page() {
    $events = get_option( CAPIGW_CUSTOM_EVENTS_KEY, array() );
    $nonce  = wp_create_nonce( 'capigw_custom_events_nonce' );
    ?>
    <style>
        .ceb-wrap { max-width: 900px; margin: 20px auto; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .ceb-header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: #fff; padding: 24px 30px; border-radius: 12px; margin-bottom: 20px; }
        .ceb-header h1 { margin: 0 0 6px; font-size: 22px; }
        .ceb-header p { margin: 0; color: #b0b0d0; font-size: 13px; }
        .ceb-card { background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); position: relative; }
        .ceb-card.disabled { opacity: 0.5; }
        .ceb-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 12px; }
        .ceb-field label { display: block; font-weight: 600; font-size: 12px; color: #555; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
        .ceb-field input, .ceb-field select { width: 100%; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
        .ceb-field input:focus, .ceb-field select:focus { border-color: #7e57c2; outline: none; box-shadow: 0 0 0 3px rgba(126,87,194,0.12); }
        .ceb-remove { position: absolute; top: 12px; right: 12px; background: #ffebee; color: #c62828; border: none; border-radius: 6px; padding: 4px 10px; font-size: 12px; cursor: pointer; }
        .ceb-remove:hover { background: #ffcdd2; }
        .ceb-toggle { position: absolute; top: 14px; right: 80px; }
        .ceb-btn { padding: 10px 24px; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.3s; }
        .ceb-btn-add { background: #16213e; color: #fff; margin-right: 10px; }
        .ceb-btn-add:hover { background: #0f3460; }
        .ceb-btn-save { background: #7e57c2; color: #fff; }
        .ceb-btn-save:hover { background: #6a3fb5; }
        .ceb-status { padding: 10px 16px; border-radius: 8px; margin-top: 12px; display: none; font-size: 13px; }
        .ceb-empty { text-align: center; padding: 40px; color: #999; }
        .ceb-hint { font-size: 11px; color: #999; margin-top: 2px; }
    </style>

    <div class="ceb-wrap">
        <div class="ceb-header">
            <h1>🎯 Custom Event Builder</h1>
            <p>আপনার নিজের কাস্টম ইভেন্ট তৈরি করুন — CSS Selector, URL Match, বা Form Submit দিয়ে ট্রিগার করুন</p>
        </div>

        <div id="ceb-events-list">
            <!-- Events will be rendered by JS -->
        </div>

        <div style="margin-top: 16px;">
            <button type="button" class="ceb-btn ceb-btn-add" onclick="cebAddEvent()">➕ Add New Event</button>
            <button type="button" class="ceb-btn ceb-btn-save" onclick="cebSaveAll()">💾 Save All Events</button>
        </div>
        <div id="ceb-status" class="ceb-status"></div>
    </div>

    <script>
    var cebEvents = <?php echo wp_json_encode( $events ); ?>;

    function cebRender() {
        var container = document.getElementById('ceb-events-list');
        if (cebEvents.length === 0) {
            container.innerHTML = '<div class="ceb-empty">🎯 কোনো কাস্টম ইভেন্ট নেই। "Add New Event" ক্লিক করুন।</div>';
            return;
        }

        var html = '';
        cebEvents.forEach(function(ev, i) {
            var disabledClass = ev.enabled ? '' : ' disabled';
            html += '<div class="ceb-card' + disabledClass + '" id="ceb-card-' + i + '">';
            html += '<button class="ceb-remove" onclick="cebRemove(' + i + ')">🗑️ Remove</button>';
            html += '<div class="ceb-toggle"><label style="font-size:12px;cursor:pointer;"><input type="checkbox" ' + (ev.enabled ? 'checked' : '') + ' onchange="cebToggle(' + i + ', this.checked)"> Active</label></div>';

            html += '<div class="ceb-row">';
            html += '<div class="ceb-field"><label>Event Name</label><input type="text" value="' + escHtml(ev.name) + '" onchange="cebUpdate(' + i + ',\'name\',this.value)" placeholder="e.g. WishlistAdd, CouponUsed"><div class="ceb-hint">Facebook-এ যে নামে পাঠাবে</div></div>';
            html += '<div class="ceb-field"><label>Trigger Type</label><select onchange="cebUpdate(' + i + ',\'trigger\',this.value); cebRender();">';
            html += '<option value="click"' + (ev.trigger === 'click' ? ' selected' : '') + '>🖱️ CSS Selector Click</option>';
            html += '<option value="url"' + (ev.trigger === 'url' ? ' selected' : '') + '>🔗 URL Pattern Match</option>';
            html += '<option value="form"' + (ev.trigger === 'form' ? ' selected' : '') + '>📝 Form Submit</option>';
            html += '<option value="timer"' + (ev.trigger === 'timer' ? ' selected' : '') + '>⏱️ Time on Page (Timer)</option>';
            html += '</select></div>';
            html += '</div>';

            html += '<div class="ceb-row">';
            if (ev.trigger === 'url') {
                html += '<div class="ceb-field"><label>URL Pattern</label><input type="text" value="' + escHtml(ev.url_pattern) + '" onchange="cebUpdate(' + i + ',\'url_pattern\',this.value)" placeholder="/thank-you/ or /success/"><div class="ceb-hint">URL-এ এই টেক্সট থাকলে ইভেন্ট ফায়ার হবে</div></div>';
            } else if (ev.trigger === 'timer') {
                html += '<div class="ceb-field"><label>Time (Seconds)</label><input type="number" value="' + escHtml(ev.selector) + '" onchange="cebUpdate(' + i + ',\'selector\',this.value)" placeholder="30"><div class="ceb-hint">কত সেকেন্ড পর ইভেন্ট ফায়ার হবে (যেমন: 30)</div></div>';
            } else {
                html += '<div class="ceb-field"><label>CSS Selector</label><input type="text" value="' + escHtml(ev.selector) + '" onchange="cebUpdate(' + i + ',\'selector\',this.value)" placeholder=".wishlist-btn, #apply-coupon"><div class="ceb-hint">এই element-এ ক্লিক/সাবমিট করলে ইভেন্ট ফায়ার হবে</div></div>';
            }
            html += '<div class="ceb-field"><label>Custom Parameter</label><input type="text" value="' + escHtml(ev.custom_param) + '" onchange="cebUpdate(' + i + ',\'custom_param\',this.value)" placeholder="e.g. coupon_code, video_name"><div class="ceb-hint">ঐচ্ছিক — custom_data তে পাঠাবে</div></div>';
            html += '</div>';

            html += '<div class="ceb-row">';
            html += '<div class="ceb-field"><label>Value (Amount)</label><input type="number" step="0.01" value="' + (ev.value || '') + '" onchange="cebUpdate(' + i + ',\'value\',parseFloat(this.value)||0)" placeholder="0.00"></div>';
            html += '<div class="ceb-field"><label>Currency</label><input type="text" value="' + escHtml(ev.currency) + '" onchange="cebUpdate(' + i + ',\'currency\',this.value)" placeholder="BDT"></div>';
            html += '</div>';

            html += '</div>';
        });
        container.innerHTML = html;
    }

    function cebAddEvent() {
        cebEvents.push({
            name: '', trigger: 'click', selector: '', url_pattern: '',
            value: 0, currency: 'BDT', custom_param: '', enabled: true
        });
        cebRender();
    }

    function cebRemove(i) {
        if (!confirm('এই ইভেন্টটি মুছে ফেলবেন?')) return;
        cebEvents.splice(i, 1);
        cebRender();
    }

    function cebToggle(i, val) { cebEvents[i].enabled = val; cebRender(); }
    function cebUpdate(i, key, val) { cebEvents[i][key] = val; }

    function escHtml(s) {
        var d = document.createElement('div');
        d.appendChild(document.createTextNode(s || ''));
        return d.innerHTML;
    }

    function cebSaveAll() {
        var status = document.getElementById('ceb-status');
        status.style.display = 'block';
        status.style.background = '#fff3e0';
        status.style.color = '#e65100';
        status.textContent = '⏳ Saving...';

        var formData = new FormData();
        formData.append('action', 'capigw_save_custom_events');
        formData.append('nonce', '<?php echo $nonce; ?>');
        formData.append('events', JSON.stringify(cebEvents));

        fetch(ajaxurl, { method: 'POST', body: formData })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                status.style.background = '#e8f5e9';
                status.style.color = '#2e7d32';
                status.textContent = '✅ সব ইভেন্ট সেভ হয়েছে!';
            } else {
                status.style.background = '#ffebee';
                status.style.color = '#c62828';
                status.textContent = '❌ Error: ' + data.data;
            }
            setTimeout(function() { status.style.display = 'none'; }, 3000);
        });
    }

    cebRender();
    </script>
    <?php
}


// ─── Frontend: Inject Custom Event Tracking JS ─────────────────────────────────
add_action( 'wp_footer', 'capigw_inject_custom_events_js', 99 );

function capigw_inject_custom_events_js() {
    $settings = capigw_get_settings();
    if ( empty( $settings['api_key'] ) ) {
        return;
    }

    $events = get_option( CAPIGW_CUSTOM_EVENTS_KEY, array() );
    if ( empty( $events ) ) {
        return;
    }

    // Filter only enabled events
    $active = array_values( array_filter( $events, function( $e ) {
        return ! empty( $e['enabled'] ) && ! empty( $e['name'] );
    } ) );

    if ( empty( $active ) ) {
        return;
    }

    ?>
    <script>
    (function() {
        var customEvents = <?php echo wp_json_encode( $active ); ?>;
        var cfg = window.capigw_config || {};
        if (!cfg.ajax_url) return;

        function sendCustom(ev) {
            var formData = new FormData();
            formData.append('action', 'capigw_track_event');
            formData.append('nonce', cfg.nonce);
            formData.append('event_name', ev.name);
            var data = {};
            if (ev.value) data.value = ev.value;
            if (ev.currency) data.currency = ev.currency;
            if (ev.custom_param) data.custom_param = ev.custom_param;
            formData.append('event_data', JSON.stringify(data));
            formData.append('page_url', window.location.href);
            formData.append('fbp', getCookie('_fbp') || '');
            formData.append('fbc', getCookie('_fbc') || '');
            formData.append('ttp', getCookie('_ttp') || '');
            formData.append('ttclid', getQueryParam('ttclid') || getCookie('_ttclid') || '');
            navigator.sendBeacon
                ? navigator.sendBeacon(cfg.ajax_url, formData)
                : fetch(cfg.ajax_url, { method: 'POST', body: formData, keepalive: true });
        }

        function getCookie(n) {
            var m = document.cookie.match(new RegExp('(^| )' + n + '=([^;]+)'));
            return m ? decodeURIComponent(m[2]) : '';
        }

        function getQueryParam(n) {
            try {
                return new URLSearchParams(window.location.search).get(n) || '';
            } catch(e) {
                return '';
            }
        }

        function elementMatches(el, selector) {
            if (!selector || !el) return false;
            try {
                return !!(el.matches(selector) || el.closest(selector));
            } catch(e) {
                return false;
            }
        }

        customEvents.forEach(function(ev) {
            if (ev.trigger === 'click' && ev.selector) {
                document.addEventListener('click', function(e) {
                    if (elementMatches(e.target, ev.selector)) {
                        sendCustom(ev);
                    }
                });
            } else if (ev.trigger === 'url' && ev.url_pattern) {
                if (window.location.href.indexOf(ev.url_pattern) !== -1) {
                    sendCustom(ev);
                }
            } else if (ev.trigger === 'form' && ev.selector) {
                document.addEventListener('submit', function(e) {
                    if (elementMatches(e.target, ev.selector)) {
                        sendCustom(ev);
                    }
                });
            } else if (ev.trigger === 'timer' && ev.selector) {
                var secs = parseInt(ev.selector, 10);
                if (secs > 0) {
                    setTimeout(function() { sendCustom(ev); }, secs * 1000);
                }
            }
        });
    })();
    </script>
    <?php
}
