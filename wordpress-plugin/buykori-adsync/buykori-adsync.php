<?php
/**
 * Plugin Name:       Buykori AdSync — Server-Side Tracking
 * Plugin URI:        https://buykori.app/
 * Description:       Server-Side Facebook CAPI, TikTok, and GA4 tracking for WooCommerce with one-page landing support, SHA-256 PII hashing, and deferred purchase control.
 * Version:           1.1.8
 * Requires at least: 5.8
 * Requires PHP:      7.4
 * Author:            Buykori AdSync
 * Author URI:        https://buykori.app/
 * License:           GPL v2 or later
 * License URI:       https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain:       buykori-adsync
 * WC requires at least: 5.0
 * WC tested up to:   9.0
 */

if (!defined('ABSPATH')) {
    exit; // Exit if accessed directly
}

// ─── Plugin Constants ──────────────────────────────────────────────────────────
define('BUYKORIGW_VERSION', '1.1.8');
define('BUYKORIGW_PLUGIN_FILE', __FILE__);
define('BUYKORIGW_PLUGIN_DIR', plugin_dir_path(__FILE__));
define('BUYKORIGW_PLUGIN_URL', plugin_dir_url(__FILE__));
define('BUYKORIGW_OPTION_KEY', 'buykorigw_settings');

// Default AdSync API URL
define('BUYKORIGW_DEFAULT_GATEWAY_URL', 'https://api.buykori.app/api/v1');

// ─── Declare WooCommerce HPOS & Blocks Compatibility ──────────────────────────
add_action('before_woocommerce_init', function () {
    if (class_exists('\Automattic\WooCommerce\Utilities\FeaturesUtil')) {
        \Automattic\WooCommerce\Utilities\FeaturesUtil::declare_compatibility(
            'custom_order_tables',
            BUYKORIGW_PLUGIN_FILE,
            true
        );
        \Automattic\WooCommerce\Utilities\FeaturesUtil::declare_compatibility(
            'cart_checkout_blocks',
            BUYKORIGW_PLUGIN_FILE,
            true
        );
    }
});

// ─── Activation Hook ───────────────────────────────────────────────────────────
register_activation_hook(__FILE__, 'buykorigw_activate');

function buykorigw_activate()
{
    // Set default options if not already set
    if (!get_option(BUYKORIGW_OPTION_KEY)) {
        $defaults = array(
            'api_key' => '',
            'gateway_url' => BUYKORIGW_DEFAULT_GATEWAY_URL,
            // Core Events
            'enable_pageview' => 1,
            'enable_lead' => 0,
            'enable_search' => 0,
            // WooCommerce Events
            'enable_viewcontent' => 1,
            'enable_addtocart' => 1,
            'enable_viewcart' => 0,
            'enable_removefromcart' => 0,
            'enable_checkout' => 1,
            'enable_addpaymentinfo' => 0,
            'enable_purchase' => 1,
            // Advanced
            'tracking_mode' => 'standard',
            'deferred_purchase' => 0,  // 1 = hold purchase until order completed
            'auto_confirm_status' => 'completed', // wc status that triggers confirm
            'debug_mode' => 0,
        );
        update_option(BUYKORIGW_OPTION_KEY, $defaults);
    }
}

// ─── Deactivation Hook ─────────────────────────────────────────────────────────
register_deactivation_hook(__FILE__, 'buykorigw_deactivate');

function buykorigw_deactivate()
{
    // Clean up scheduled actions if any
    if (function_exists('as_unschedule_all_actions')) {
        as_unschedule_all_actions('buykorigw_retry_confirm');
    }

    // প্লাগিন বন্ধ করলে ক্যাশ ক্লিয়ার করে দাও যাতে ট্র্যাকিং স্ক্রিপ্ট সঙ্গে সঙ্গে সরে যায়
    buykorigw_purge_all_caches();
}

// ─── Auto-Purge Cache on Settings Save ────────────────────────────────────────
// সেটিংস সেভ করার সাথে সাথে ক্যাশ ক্লিয়ার করে দাও
add_action('update_option_' . BUYKORIGW_OPTION_KEY, 'buykorigw_purge_all_caches', 10, 0);

/**
 * buykorigw_purge_all_caches()
 *
 * WP Rocket, LiteSpeed, W3 Total Cache, WP Super Cache,
 * SiteGround Optimizer, WP Fastest Cache এবং Autoptimize-র
 * ক্যাশ স্বয়ংক্রিয়ভাবে ক্লিয়ার করে।
 *
 * যখন Buykori AdSync সেটিংস পরিবর্তন হয় বা প্লাগিন ডিঅ্যাক্টিভেট হয়,
 * তখন এই ফাংশনটি কল হয়।
 */
function buykorigw_purge_all_caches()
{
    $purged = array();

    // ── WP Rocket ──────────────────────────────────────────────────────
    if (function_exists('rocket_clean_domain')) {
        rocket_clean_domain();
        $purged[] = 'WP Rocket';
    }

    // ── LiteSpeed Cache ─────────────────────────────────────────────────
    if (class_exists('\LiteSpeed\Purge')) {
        do_action('litespeed_purge_all');
        $purged[] = 'LiteSpeed Cache';
    } elseif (defined('LSCWP_V')) {
        do_action('litespeed_purge_all');
        $purged[] = 'LiteSpeed Cache';
    }

    // ── W3 Total Cache ──────────────────────────────────────────────────
    if (function_exists('w3tc_flush_all')) {
        w3tc_flush_all();
        $purged[] = 'W3 Total Cache';
    }

    // ── WP Super Cache ──────────────────────────────────────────────────
    if (function_exists('wp_cache_clear_cache')) {
        wp_cache_clear_cache();
        $purged[] = 'WP Super Cache';
    }

    // ── SiteGround Optimizer ────────────────────────────────────────────
    if (class_exists('SiteGround_Optimizer\Supercacher\Supercacher')) {
        \SiteGround_Optimizer\Supercacher\Supercacher::purge_cache();
        $purged[] = 'SiteGround Optimizer';
    }

    // ── WP Fastest Cache ────────────────────────────────────────────────
    if (isset($GLOBALS['wp_fastest_cache']) && method_exists($GLOBALS['wp_fastest_cache'], 'deleteCache')) {
        $GLOBALS['wp_fastest_cache']->deleteCache(true);
        $purged[] = 'WP Fastest Cache';
    }

    // ── Autoptimize ─────────────────────────────────────────────────────
    if (class_exists('autoptimizeCache') && method_exists('autoptimizeCache', 'clearall')) {
        autoptimizeCache::clearall();
        $purged[] = 'Autoptimize';
    }

    // ── Breeze (Cloudways) ──────────────────────────────────────────────
    if (class_exists('Breeze_Admin')) {
        do_action('breeze_clear_all_cache');
        $purged[] = 'Breeze';
    }

    // ── Swift Performance ───────────────────────────────────────────────
    if (class_exists('Swift_Performance_Cache') && method_exists('Swift_Performance_Cache', 'clear_all_cache')) {
        \Swift_Performance_Cache::clear_all_cache();
        $purged[] = 'Swift Performance';
    }

    // ── Generic WordPress Object Cache (Memcache / Redis) ───────────────
    wp_cache_flush();

    if (!empty($purged)) {
        error_log('[Buykori AdSync] Cache purged: ' . implode(', ', $purged));
    }
}

// ─── Helper: Get Plugin Settings ───────────────────────────────────────────────
function buykorigw_get_settings()
{
    $settings = get_option(BUYKORIGW_OPTION_KEY, array());
    return wp_parse_args($settings, array(
        'api_key' => '',
        'gateway_url' => BUYKORIGW_DEFAULT_GATEWAY_URL,
        // Core Events
        'enable_pageview' => 1,
        'enable_lead' => 0,
        'enable_search' => 0,
        // WooCommerce Events
        'enable_viewcontent' => 1,
        'enable_addtocart' => 1,
        'enable_viewcart' => 0,
        'enable_removefromcart' => 0,
        'enable_checkout' => 1,
        'enable_addpaymentinfo' => 0,
        'enable_purchase' => 1,
        // Advanced
        'tracking_mode' => 'standard',
        'deferred_purchase' => 0,
        'auto_confirm_status' => 'completed',
        'debug_mode' => 0,
    ));
}

function buykorigw_site_origin()
{
    $parts = wp_parse_url(home_url());
    if (empty($parts['host'])) {
        return '';
    }
    $scheme = !empty($parts['scheme']) ? $parts['scheme'] : 'https';
    return $scheme . '://' . strtolower($parts['host']);
}

function buykorigw_signed_headers($api_key, $body)
{
    $timestamp = (string) time();
    $signature = hash_hmac('sha256', $timestamp . '.' . $body, $api_key);

    return array(
        'X-CAPI-Origin' => buykorigw_site_origin(),
        'X-CAPI-Timestamp' => $timestamp,
        'X-CAPI-Signature' => $signature,
    );
}

function buykorigw_normalize_host($host)
{
    $host = strtolower(trim((string) $host));
    if (strpos($host, 'www.') === 0) {
        $host = substr($host, 4);
    }
    return $host;
}

function buykorigw_host_allowed($request_host, $allowed_host)
{
    $request_host = buykorigw_normalize_host($request_host);
    $allowed_host = buykorigw_normalize_host($allowed_host);

    if (empty($request_host) || empty($allowed_host)) {
        return false;
    }

    if ($request_host === $allowed_host) {
        return true;
    }

    $suffix = '.' . $allowed_host;
    return substr($request_host, -strlen($suffix)) === $suffix;
}

// ─── Helper: Send Event to Buykori AdSync (Server-Side via wp_remote_post) ─────
function buykorigw_send_event($event_data, $blocking = true)
{
    $settings = buykorigw_get_settings();

    if (empty($settings['api_key']) || empty($settings['gateway_url'])) {
        if ($settings['debug_mode']) {
            error_log('[Buykori AdSync] API Key or AdSync API URL is missing.');
        }
        return false;
    }

    $url = rtrim($settings['gateway_url'], '/') . '/events';

    $body = wp_json_encode(array('data' => array($event_data)));

    $headers = array_merge(array(
        'Content-Type' => 'application/json',
        'X-API-Key' => $settings['api_key'],
    ), buykorigw_signed_headers($settings['api_key'], $body));

    $response = wp_remote_post($url, array(
        'timeout' => 10,
        'redirection' => 0,
        'httpversion' => '1.1',
        'blocking' => (bool) $blocking,
        'sslverify' => true,
        'headers' => $headers,
        'body' => $body,
    ));

    if (is_wp_error($response)) {
        if ($settings['debug_mode']) {
            error_log('[Buykori AdSync] Send failed: ' . $response->get_error_message());
        }
        return false;
    }

    if ($blocking) {
        $code = wp_remote_retrieve_response_code($response);
        if ($code < 200 || $code >= 300) {
            if ($settings['debug_mode']) {
                error_log('[Buykori AdSync] Send HTTP ' . $code . ': ' . wp_remote_retrieve_body($response));
            }
            return false;
        }
    }

    return true;
}

// ─── Helper: SHA-256 Hash (for PII fields) ─────────────────────────────────────
function buykorigw_hash($value)
{
    if (empty($value)) {
        return '';
    }
    $value = strtolower(trim($value));
    // Don't double-hash (already hashed values are 64 chars hex)
    if (preg_match('/^[a-f0-9]{64}$/', $value)) {
        return $value;
    }
    return hash('sha256', $value);
}

function buykorigw_hash_phone($value)
{
    if (empty($value)) {
        return '';
    }
    $value = strtolower(trim($value));
    if (preg_match('/^[a-f0-9]{64}$/', $value)) {
        return $value;
    }
    $value = preg_replace('/[^0-9]/', '', $value);
    $value = ltrim($value, '0');
    return buykorigw_hash($value);
}

// ─── Load Sub-Modules ──────────────────────────────────────────────────────────
function buykorigw_get_order_meta($order_id, $key)
{
    if (function_exists('wc_get_order')) {
        $order = wc_get_order($order_id);
        if ($order) {
            return $order->get_meta($key, true);
        }
    }

    return get_post_meta($order_id, $key, true);
}

function buykorigw_update_order_meta($order_id, $key, $value)
{
    if (function_exists('wc_get_order')) {
        $order = wc_get_order($order_id);
        if ($order) {
            $order->update_meta_data($key, $value);
            $order->save();
            return;
        }
    }

    update_post_meta($order_id, $key, $value);
}

// Admin settings page
if (is_admin()) {
    require_once BUYKORIGW_PLUGIN_DIR . 'includes/admin-settings.php';
    require_once BUYKORIGW_PLUGIN_DIR . 'includes/dashboard-widget.php';
}

// Frontend tracking (only on frontend, not admin/cron, but allow AJAX)
if (!is_admin() || wp_doing_ajax()) {
    require_once BUYKORIGW_PLUGIN_DIR . 'includes/frontend-tracking.php';
}

// Custom events (admin UI + frontend JS — loads in both contexts)
require_once BUYKORIGW_PLUGIN_DIR . 'includes/custom-events.php';

// WooCommerce order hooks (always load — works via WP-Cron and admin)
if (class_exists('WooCommerce') || in_array('woocommerce/woocommerce.php', apply_filters('active_plugins', get_option('active_plugins')))) {
    require_once BUYKORIGW_PLUGIN_DIR . 'includes/woo-order-hooks.php';
}

// Auto-updater (check for plugin updates from our server)
if (is_admin()) {
    require_once BUYKORIGW_PLUGIN_DIR . 'includes/auto-updater.php';
}
