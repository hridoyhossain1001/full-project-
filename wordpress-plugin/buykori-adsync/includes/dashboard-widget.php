<?php
/**
 * Buykori AdSync — Dashboard Widget
 *
 * WordPress Admin হোমপেজে একটি সুন্দর ড্যাশবোর্ড উইজেট দেখায়।
 * আজকের ট্র্যাকিং সামারি — মোট ইভেন্ট, সাকসেস রেট, টপ ইভেন্ট, কানেকশন স্ট্যাটাস।
 */

if (!defined('ABSPATH')) {
    exit;
}

// ─── Register Dashboard Widget ─────────────────────────────────────────────────
add_action('wp_dashboard_setup', 'buykorigw_add_dashboard_widget');

function buykorigw_add_dashboard_widget()
{
    $settings = buykorigw_get_settings();
    if (empty($settings['api_key'])) {
        return;
    }

    wp_add_dashboard_widget(
        'buykorigw_dashboard_widget',
        '⚡ Buykori AdSync — Tracking Overview',
        'buykorigw_dashboard_widget_render'
    );
}

// ─── Widget Render ─────────────────────────────────────────────────────────────
function buykorigw_dashboard_widget_render()
{
    $settings = buykorigw_get_settings();
    $nonce = wp_create_nonce('buykorigw_widget_nonce');
    ?>
    <style>
        .cgw-wrap {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        .cgw-stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 14px;
        }

        .cgw-stat {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 14px;
            text-align: center;
        }

        .cgw-stat .num {
            font-size: 24px;
            font-weight: 700;
            color: #1a1a2e;
        }

        .cgw-stat .label {
            font-size: 11px;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 2px;
        }

        .cgw-stat.success .num {
            color: #2e7d32;
        }

        .cgw-stat.warning .num {
            color: #f57c00;
        }

        .cgw-stat.error .num {
            color: #c62828;
        }

        .cgw-stat.info .num {
            color: #7e57c2;
        }

        .cgw-conn {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 14px;
        }

        .cgw-conn.online {
            background: #e8f5e9;
            color: #2e7d32;
        }

        .cgw-conn.offline {
            background: #ffebee;
            color: #c62828;
        }

        .cgw-conn .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }

        .cgw-conn.online .dot {
            background: #2e7d32;
            animation: cgwPulse 2s infinite;
        }

        .cgw-conn.offline .dot {
            background: #c62828;
        }

        @keyframes cgwPulse {

            0%,
            100% {
                opacity: 1;
            }

            50% {
                opacity: 0.4;
            }
        }

        .cgw-events {
            margin-top: 12px;
        }

        .cgw-event-row {
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            border-bottom: 1px solid #f0f0f0;
            font-size: 13px;
        }

        .cgw-event-row:last-child {
            border: none;
        }

        .cgw-event-name {
            color: #333;
            font-weight: 500;
        }

        .cgw-event-count {
            color: #7e57c2;
            font-weight: 600;
        }

        .cgw-loading {
            text-align: center;
            padding: 20px;
            color: #999;
        }

        .cgw-footer {
            margin-top: 14px;
            text-align: center;
        }

        .cgw-footer a {
            color: #7e57c2;
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
        }

        .cgw-footer a:hover {
            text-decoration: underline;
        }
    </style>

    <div class="cgw-wrap">
        <div id="cgw-content">
            <div class="cgw-loading">⏳ Loading tracking data...</div>
        </div>
        <div class="cgw-footer">
            <a href="<?php echo admin_url('admin.php?page=buykori-adsync'); ?>">⚙️ Plugin Settings</a>
        </div>
    </div>

    <script>
        (function () {
            function cgwEscape(value) {
                var div = document.createElement('div');
                div.textContent = value == null ? '' : String(value);
                return div.innerHTML;
            }

            function cgwNumber(value) {
                var number = Number(value);
                return Number.isFinite(number) ? number : 0;
            }

            var formData = new FormData();
            formData.append('action', 'buykorigw_widget_data');
            formData.append('nonce', '<?php echo $nonce; ?>');

            fetch(ajaxurl, { method: 'POST', body: formData })
                .then(function (r) { return r.json(); })
                .then(function (resp) {
                    if (!resp.success) {
                        document.getElementById('cgw-content').innerHTML = '<div class="cgw-loading" style="color:#c62828;">❌ ' + (resp.data || 'Error loading data') + '</div>';
                        return;
                    }
                    var d = resp.data;
                    var html = '';

                    // Connection status
                    html += '<div class="cgw-conn ' + (d.server_online ? 'online' : 'offline') + '">';
                    html += '<span class="dot"></span>';
                    html += d.server_online ? 'Server Connected' : 'Server Offline';
                    html += '</div>';

                    // Stats grid
                    html += '<div class="cgw-stats">';
                    html += '<div class="cgw-stat info"><div class="num">' + cgwNumber(d.total_today) + '</div><div class="label">Today\'s Events</div></div>';
                    html += '<div class="cgw-stat success"><div class="num">' + cgwNumber(d.success_rate) + '%</div><div class="label">Success Rate</div></div>';
                    html += '<div class="cgw-stat warning"><div class="num">' + cgwNumber(d.pending_orders) + '</div><div class="label">Pending Orders</div></div>';
                    html += '<div class="cgw-stat"><div class="num">' + cgwNumber(d.total_month) + '</div><div class="label">This Month</div></div>';
                    html += '</div>';

                    // Top events
                    if (d.top_events && d.top_events.length > 0) {
                        html += '<div class="cgw-events"><strong style="font-size:12px;color:#888;text-transform:uppercase;">Top Events (Today)</strong>';
                        d.top_events.forEach(function (ev) {
                            html += '<div class="cgw-event-row"><span class="cgw-event-name">' + cgwEscape(ev.name) + '</span><span class="cgw-event-count">' + cgwNumber(ev.count) + '</span></div>';
                        });
                        html += '</div>';
                    }

                    document.getElementById('cgw-content').innerHTML = html;
                })
                .catch(function (err) {
                    document.getElementById('cgw-content').innerHTML = '<div class="cgw-loading" style="color:#c62828;">❌ Network error</div>';
                });
        })();
    </script>
    <?php
}


// ─── AJAX: Fetch Widget Data ───────────────────────────────────────────────────
add_action('wp_ajax_buykorigw_widget_data', 'buykorigw_widget_data');

function buykorigw_widget_data()
{
    check_ajax_referer('buykorigw_widget_nonce', 'nonce');

    if (!current_user_can('manage_options')) {
        wp_send_json_error('Permission denied');
    }

    $settings = buykorigw_get_settings();

    if (empty($settings['api_key']) || empty($settings['gateway_url'])) {
        wp_send_json_error('API Key not configured');
    }

    // Fetch overview from gateway analytics API
    $base_url = rtrim($settings['gateway_url'], '/');
    $data = array(
        'server_online' => false,
        'total_today' => 0,
        'total_month' => 0,
        'success_rate' => 0,
        'pending_orders' => 0,
        'top_events' => array(),
    );

    // 1. Check server health
    $health = wp_remote_get($base_url . '/health', array(
        'timeout' => 5,
        'sslverify' => true,
        'headers' => array('X-API-Key' => $settings['api_key']),
    ));

    if (!is_wp_error($health) && wp_remote_retrieve_response_code($health) === 200) {
        $data['server_online'] = true;
    }

    // 2. Get analytics overview (today)
    $overview = wp_remote_get($base_url . '/analytics/overview?days=1', array(
        'timeout' => 8,
        'sslverify' => true,
        'headers' => array('X-API-Key' => $settings['api_key']),
    ));

    if (!is_wp_error($overview) && wp_remote_retrieve_response_code($overview) === 200) {
        $body = json_decode(wp_remote_retrieve_body($overview), true);

        if ($body) {
            $data['total_today'] = $body['total_events'] ?? 0;
            $data['success_rate'] = $body['success_rate'] ?? 0;

            // Top events from breakdown
            if (!empty($body['event_breakdown'])) {
                $top = array_slice($body['event_breakdown'], 0, 5);
                foreach ($top as $ev) {
                    $data['top_events'][] = array(
                        'name' => $ev['event_name'] ?? 'Unknown',
                        'count' => $ev['count'] ?? 0,
                    );
                }
            }
        }
    }

    // 3. Get monthly total (30 days)
    $monthly = wp_remote_get($base_url . '/analytics/overview?days=30', array(
        'timeout' => 8,
        'sslverify' => true,
        'headers' => array('X-API-Key' => $settings['api_key']),
    ));

    if (!is_wp_error($monthly) && wp_remote_retrieve_response_code($monthly) === 200) {
        $mbody = json_decode(wp_remote_retrieve_body($monthly), true);
        if ($mbody) {
            $data['total_month'] = $mbody['total_events'] ?? 0;
        }
    }

    // 4. Get pending orders count
    $pending = wp_remote_get($base_url . '/events/pending?limit=1', array(
        'timeout' => 5,
        'sslverify' => true,
        'headers' => array('X-API-Key' => $settings['api_key']),
    ));

    if (!is_wp_error($pending) && wp_remote_retrieve_response_code($pending) === 200) {
        $pbody = json_decode(wp_remote_retrieve_body($pending), true);
        if ($pbody) {
            $data['pending_orders'] = $pbody['total'] ?? 0;
        }
    }

    wp_send_json_success($data);
}
