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
            color: #1e293b;
        }

        .cgw-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }

        .cgw-stat {
            background: #f8fafc;
            border: 1px solid #f1f5f9;
            border-radius: 8px;
            padding: 14px 10px;
            text-align: center;
            box-shadow: 0 1px 3px 0 rgba(0,0,0,0.05);
            transition: all 0.2s ease-in-out;
        }

        .cgw-stat:hover {
            transform: translateY(-2px);
            background: #ffffff;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -1px rgba(0,0,0,0.04);
            border-color: #cbd5e1;
        }

        .cgw-stat .num {
            font-size: 20px;
            font-weight: 800;
            color: #0f172a;
            line-height: 1.2;
        }

        .cgw-stat .label {
            font-size: 10px;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 6px;
            font-weight: 600;
        }

        .cgw-stat.success .num {
            color: #059669;
        }

        .cgw-stat.warning .num {
            color: #d97706;
        }

        .cgw-stat.error .num {
            color: #dc2626;
        }

        .cgw-stat.info .num {
            color: #4f46e5;
        }

        .cgw-alert {
            background: #fffbeb;
            border: 1px solid #fef3c7;
            border-left: 4px solid #d97706;
            color: #92400e;
            border-radius: 8px;
            padding: 12px;
            font-size: 12px;
            line-height: 1.5;
            margin-bottom: 16px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.02);
        }

        .cgw-risk {
            border: 1px solid #fed7aa;
            border-left: 4px solid #ea580c;
            border-radius: 8px;
            padding: 14px;
            margin-bottom: 16px;
            background: #fff7ed;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02);
        }

        .cgw-risk-head {
            display: flex;
            justify-content: space-between;
            gap: 10px;
            align-items: flex-start;
        }

        .cgw-risk-title {
            color: #c2410c;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .cgw-risk-value {
            color: #0f172a;
            font-size: 24px;
            font-weight: 800;
            line-height: 1.1;
            margin-top: 4px;
        }

        .cgw-risk-meta {
            color: #475569;
            font-size: 12px;
            margin-top: 8px;
            line-height: 1.5;
        }

        .cgw-conn {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 16px;
            font-weight: 600;
            box-shadow: 0 1px 2px rgba(0,0,0,0.02);
        }

        .cgw-conn.online {
            background: #ecfdf5;
            color: #065f46;
            border: 1px solid #a7f3d0;
        }

        .cgw-conn.offline {
            background: #fef2f2;
            color: #991b1b;
            border: 1px solid #fecaca;
        }

        .cgw-conn .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }

        .cgw-conn.online .dot {
            background: #059669;
            animation: cgwPulse 2s infinite;
        }

        .cgw-conn.offline .dot {
            background: #dc2626;
        }

        @keyframes cgwPulse {
            0%, 100% {
                opacity: 1;
                transform: scale(1);
            }
            50% {
                opacity: 0.4;
                transform: scale(1.2);
            }
        }

        .cgw-events {
            margin-top: 14px;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 14px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02);
        }

        .cgw-event-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #f1f5f9;
            font-size: 13px;
        }

        .cgw-event-row:last-child {
            border: none;
        }

        .cgw-event-name {
            color: #334155;
            font-weight: 500;
        }

        .cgw-event-count {
            color: #4f46e5;
            font-weight: 700;
            background: #eef2ff;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 11px;
        }

        .cgw-loading {
            text-align: center;
            padding: 32px 16px;
            color: #64748b;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 12px;
            font-weight: 500;
        }

        .cgw-spinner {
            width: 28px;
            height: 28px;
            border: 3px solid #e2e8f0;
            border-top: 3px solid #4f46e5;
            border-radius: 50%;
            animation: cgwSpin 0.8s linear infinite;
        }

        @keyframes cgwSpin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .cgw-footer {
            margin-top: 16px;
            text-align: center;
        }

        .cgw-footer a {
            color: #4f46e5;
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
            transition: color 0.15s ease-in-out;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .cgw-footer a:hover {
            color: #4338ca;
            text-decoration: underline;
        }

        @media (max-width: 480px) {
            .cgw-stats {
                grid-template-columns: 1fr;
            }
        }
    </style>

    <div class="cgw-wrap">
        <div id="cgw-content">
            <div class="cgw-loading">
                <div class="cgw-spinner"></div>
                <span>⏳ Loading tracking data...</span>
            </div>
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

            function cgwMoney(value) {
                return 'BDT ' + cgwNumber(value).toLocaleString();
            }

            var formData = new FormData();
            formData.append('action', 'buykorigw_widget_data');
            formData.append('nonce', '<?php echo $nonce; ?>');

            fetch(ajaxurl, { method: 'POST', body: formData })
                .then(function (r) { return r.json(); })
                .then(function (resp) {
                    if (!resp.success) {
                        document.getElementById('cgw-content').innerHTML = '<div class="cgw-loading" style="color:#dc2626;">❌ ' + cgwEscape(resp.data || 'Error loading data') + '</div>';
                        return;
                    }
                    var d = resp.data;
                    var html = '';

                    // Connection status
                    html += '<div class="cgw-conn ' + (d.server_online ? 'online' : 'offline') + '">';
                    html += '<span class="dot"></span>';
                    html += d.server_online ? 'Server Connected' : 'Server Offline';
                    html += '</div>';

                    if (cgwNumber(d.pending_orders) > 0) {
                        html += '<div class="cgw-risk">';
                        html += '<div class="cgw-risk-head">';
                        html += '<div><div class="cgw-risk-title">Pending revenue at risk</div>';
                        html += '<div class="cgw-risk-value">' + cgwMoney(d.pending_value) + '</div></div>';
                        html += '<div style="text-align:right;color:#ea580c;font-weight:700;">' + cgwNumber(d.pending_orders) + ' COD</div>';
                        html += '</div>';
                        html += '<div class="cgw-risk-meta">These orders are held until verification, so fake or cancelled COD orders do not train Meta/TikTok.';
                        if (cgwNumber(d.pending_oldest_age_hours) > 0) {
                            html += '<br>Oldest pending order: ' + cgwNumber(d.pending_oldest_age_hours) + 'h';
                        }
                        html += '</div></div>';
                    }

                    // Stats grid
                    html += '<div class="cgw-stats">';
                    html += '<div class="cgw-stat info"><div class="num">' + cgwNumber(d.total_today) + '</div><div class="label">Today\'s Events</div></div>';
                    html += '<div class="cgw-stat success"><div class="num">' + cgwNumber(d.success_rate) + '%</div><div class="label">Success Rate</div></div>';
                    html += '<div class="cgw-stat warning"><div class="num">' + cgwNumber(d.pending_orders) + '</div><div class="label">Pending COD</div></div>';
                    html += '<div class="cgw-stat success"><div class="num">' + cgwNumber(d.verified_purchases) + '</div><div class="label">Verified Purchases</div></div>';
                    html += '<div class="cgw-stat error"><div class="num">' + cgwNumber(d.cancelled_or_expired) + '</div><div class="label">Cancelled / Expired</div></div>';
                    html += '<div class="cgw-stat warning"><div class="num" style="font-size:16px;">' + cgwMoney(d.pending_value) + '</div><div class="label">Revenue At Risk</div></div>';
                    html += '<div class="cgw-stat"><div class="num">' + cgwNumber(d.total_month) + '</div><div class="label">This Month</div></div>';
                    html += '</div>';

                    if (cgwNumber(d.pending_oldest_age_hours) >= 24) {
                        html += '<div class="cgw-alert">⚠️ Oldest COD order is ' + cgwNumber(d.pending_oldest_age_hours) + 'h pending. Confirm or cancel it so ad platforms learn from verified purchases only.</div>';
                    }

                    // Top events
                    if (d.top_events && d.top_events.length > 0) {
                        html += '<div class="cgw-events"><strong style="font-size:12px;color:#64748b;text-transform:uppercase;">Top Events (Today)</strong>';
                        d.top_events.forEach(function (ev) {
                            html += '<div class="cgw-event-row"><span class="cgw-event-name">' + cgwEscape(ev.name) + '</span><span class="cgw-event-count">' + cgwNumber(ev.count) + '</span></div>';
                        });
                        html += '</div>';
                    }

                    document.getElementById('cgw-content').innerHTML = html;
                })
                .catch(function (err) {
                    document.getElementById('cgw-content').innerHTML = '<div class="cgw-loading" style="color:#dc2626;">❌ Network error</div>';
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
        'verified_purchases' => 0,
        'cancelled_or_expired' => 0,
        'pending_value' => 0,
        'pending_oldest_age_hours' => null,
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

    // 4. Get verified purchase / COD summary
    $pending_summary = wp_remote_get($base_url . '/events/deferred/summary', array(
        'timeout' => 5,
        'sslverify' => true,
        'headers' => array('X-API-Key' => $settings['api_key']),
    ));

    if (!is_wp_error($pending_summary) && wp_remote_retrieve_response_code($pending_summary) === 200) {
        $pbody = json_decode(wp_remote_retrieve_body($pending_summary), true);
        if ($pbody) {
            $data['pending_orders'] = $pbody['pending'] ?? 0;
            $data['verified_purchases'] = $pbody['confirmed'] ?? 0;
            $data['cancelled_or_expired'] = ($pbody['cancelled'] ?? 0) + ($pbody['expired'] ?? 0);
            $data['pending_value'] = $pbody['pending_value'] ?? 0;
            $data['pending_oldest_age_hours'] = $pbody['pending_oldest_age_hours'] ?? null;
        }
    } else {
        // Backward-compatible fallback for older servers.
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
    }

    wp_send_json_success($data);
}
