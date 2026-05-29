<?php
/**
 * Buykori AdSync — Plugin Auto-Update
 *
 * আপনার সার্ভার থেকে প্লাগইনের নতুন ভার্সন চেক করে।
 * WordPress Dashboard থেকে ওয়ান-ক্লিকে আপডেট করার সুবিধা দেয়।
 *
 * কাজের ধরন:
 * 1. WordPress যখন প্লাগইন আপডেট চেক করে, আমরা আমাদের সার্ভারে একটি
 *    রিকোয়েস্ট পাঠাই — নতুন ভার্সন আছে কিনা দেখতে।
 * 2. নতুন ভার্সন থাকলে WordPress-এর স্ট্যান্ডার্ড আপডেট নোটিফিকেশন দেখায়।
 * 3. "Update Now" ক্লিক করলে সার্ভার থেকে ZIP ডাউনলোড করে ইন্সটল করে।
 */

if (!defined('ABSPATH')) {
    exit;
}

function buykorigw_clear_update_cache()
{
    $settings = buykorigw_get_settings();
    $cache_key = 'buykorigw_update_info_' . md5($settings['api_key'] ?? '');

    delete_transient($cache_key);
    delete_site_transient('update_plugins');

    if (function_exists('wp_clean_plugins_cache')) {
        wp_clean_plugins_cache(true);
    }
}

class BUYKORIGW_Auto_Updater
{

    private $plugin_slug;
    private $plugin_file;
    private $current_version;
    private $update_url;

    public function __construct()
    {
        $this->plugin_slug = 'buykori-adsync';
        $this->plugin_file = 'buykori-adsync/buykori-adsync.php';
        $this->current_version = BUYKORIGW_VERSION;

        // Build update check URL from gateway settings
        $settings = buykorigw_get_settings();
        $gateway = rtrim($settings['gateway_url'], '/');
        // Remove /api/v1 to get base URL
        $base_url = preg_replace('#/api/v1/?$#', '', $gateway);
        $this->update_url = $base_url . '/api/v1/plugin/update-check';

        // Hook into WordPress update system
        add_filter('pre_set_site_transient_update_plugins', array($this, 'check_for_update'));
        add_filter('plugins_api', array($this, 'plugin_info'), 20, 3);
        add_filter('upgrader_pre_download', array($this, 'verify_downloaded_package'), 10, 3);
        add_filter('upgrader_post_install', array($this, 'after_install'), 10, 3);
    }

    /**
     * Check for plugin updates — WordPress প্রতি ১২ ঘন্টায় এটি কল করে
     */
    public function check_for_update($transient)
    {
        if (empty($transient->checked)) {
            return $transient;
        }

        $remote = $this->get_remote_info();

        if ($remote && version_compare($this->current_version, $remote->version, '<')) {
            $plugin_data = new stdClass();
            $plugin_data->slug = $this->plugin_slug;
            $plugin_data->plugin = $this->plugin_file;
            $plugin_data->new_version = $remote->version;
            $plugin_data->url = $remote->homepage ?? '';
            $plugin_data->package = $remote->download_url ?? '';
            $plugin_data->tested = $remote->tested ?? '6.7';
            $plugin_data->requires = $remote->requires ?? '5.8';
            $plugin_data->requires_php = $remote->requires_php ?? '7.4';

            $transient->response[$this->plugin_file] = $plugin_data;
        }

        return $transient;
    }

    /**
     * Plugin details popup — "View Details" ক্লিক করলে যা দেখায়
     */
    public function plugin_info($result, $action, $args)
    {
        if ($action !== 'plugin_information' || $args->slug !== $this->plugin_slug) {
            return $result;
        }

        $remote = $this->get_remote_info();

        if (!$remote) {
            return $result;
        }

        $info = new stdClass();
        $info->name = 'Buykori AdSync — Server-Side Tracking';
        $info->slug = $this->plugin_slug;
        $info->version = $remote->version;
        $info->author = '<a href="' . esc_url($remote->homepage ?? '') . '">Buykori AdSync</a>';
        $info->homepage = $remote->homepage ?? '';
        $info->download_link = $remote->download_url ?? '';
        $info->tested = $remote->tested ?? '6.7';
        $info->requires = $remote->requires ?? '5.8';
        $info->requires_php = $remote->requires_php ?? '7.4';
        $info->last_updated = $remote->last_updated ?? '';
        $info->sections = array(
            'description' => $remote->description ?? 'Server-Side Facebook CAPI tracking for WooCommerce.',
            'changelog' => $remote->changelog ?? '<p>Bug fixes and improvements.</p>',
        );

        // Banner image (optional)
        if (!empty($remote->banner)) {
            $info->banners = array('high' => $remote->banner);
        }

        return $info;
    }

    /**
     * After install — ফোল্ডার নাম ঠিক করে
     */
    public function after_install($response, $hook_extra, $result)
    {
        global $wp_filesystem;

        if (!isset($hook_extra['plugin']) || $hook_extra['plugin'] !== $this->plugin_file) {
            return $result;
        }

        $install_dir = plugin_dir_path(BUYKORIGW_PLUGIN_FILE);
        $wp_filesystem->move($result['destination'], $install_dir);
        $result['destination'] = $install_dir;

        // Re-activate plugin
        activate_plugin($this->plugin_file);

        return $result;
    }

    /**
     * Fetch remote plugin info from our server — ক্যাশ সহ
     */
    private function get_remote_info()
    {
        $settings = buykorigw_get_settings();
        $cache_key = 'buykorigw_update_info_' . md5($settings['api_key'] ?? '');
        $cached = get_transient($cache_key);

        if ($cached !== false) {
            return $cached;
        }

        $response = wp_remote_get($this->update_url, array(
            'timeout' => 10,
            'sslverify' => true,
            'headers' => array(
                'X-API-Key' => $settings['api_key'] ?? '',
                'X-Plugin-Version' => $this->current_version,
            ),
        ));

        if (is_wp_error($response) || wp_remote_retrieve_response_code($response) !== 200) {
            return false;
        }

        $body = json_decode(wp_remote_retrieve_body($response));

        if (empty($body) || empty($body->version)) {
            return false;
        }

        if (!$this->verify_remote_info($body, $settings['api_key'] ?? '')) {
            return false;
        }

        // Cache for 12 hours
        set_transient($cache_key, $body, 12 * HOUR_IN_SECONDS);

        return $body;
    }

    private function verify_remote_info($remote, $api_key)
    {
        if (empty($remote->download_url) || empty($remote->package_sha256) || empty($remote->signature) || empty($api_key)) {
            return false;
        }

        if (!$this->package_url_allowed($remote->download_url)) {
            return false;
        }

        if (!preg_match('/^[a-f0-9]{64}$/', $remote->package_sha256)) {
            return false;
        }

        $payload = $remote->version . '|' . $remote->download_url . '|' . $remote->package_sha256;
        $expected = hash_hmac('sha256', $payload, $api_key);
        return hash_equals($expected, $remote->signature);
    }

    private function package_url_allowed($download_url)
    {
        $update_host = strtolower(wp_parse_url($this->update_url, PHP_URL_HOST));
        $package_host = strtolower(wp_parse_url($download_url, PHP_URL_HOST));
        $scheme = wp_parse_url($download_url, PHP_URL_SCHEME);

        if ($scheme !== 'https' || !$update_host || !$package_host) {
            return false;
        }

        // Same host (normal case)
        if ($update_host === $package_host) {
            return true;
        }

        // Allow the canonical custom domain.
        $allowed_hosts = array(
            'buykori.app',
            'www.buykori.app',
            'api.buykori.app',
        );
        if (in_array($package_host, $allowed_hosts, true)) {
            return true;
        }

        if (preg_match('/^([a-z0-9-]+\.)*(buykori\.app)$/', $package_host)) {
            return true;
        }

        return false;
    }

    public function verify_downloaded_package($reply, $package, $upgrader)
    {
        $remote = $this->get_remote_info();
        if (!$remote || empty($remote->download_url) || $package !== $remote->download_url) {
            return $reply;
        }

        $downloaded = download_url($package);
        if (is_wp_error($downloaded)) {
            return $downloaded;
        }

        $actual_hash = hash_file('sha256', $downloaded);
        if (!hash_equals($remote->package_sha256, $actual_hash)) {
            @unlink($downloaded);
            return new WP_Error('buykorigw_update_hash_mismatch', 'Buykori AdSync update package verification failed.');
        }

        return $downloaded;
    }
}

// Initialize auto-updater
new BUYKORIGW_Auto_Updater();
