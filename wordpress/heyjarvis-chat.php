<?php
/**
 * Plugin Name: HeyJarvis Chat
 * Plugin URI: https://heyjarvis.ai
 * Description: AI-powered dental concierge chat widget for appointment scheduling.
 * Version: 1.0.0
 * Author: HeyJarvis
 * License: Proprietary
 */

if (!defined('ABSPATH')) exit;

define('HEYJARVIS_VERSION', '1.0.0');
define('HEYJARVIS_PLUGIN_DIR', plugin_dir_path(__FILE__));
define('HEYJARVIS_PLUGIN_URL', plugin_dir_url(__FILE__));

class HeyJarvis_Chat {
    private static $instance = null;

    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    private function __construct() {
        add_action('init', [$this, 'init']);
        add_action('admin_menu', [$this, 'admin_menu']);
        add_action('wp_enqueue_scripts', [$this, 'enqueue_scripts']);
        add_action('wp_footer', [$this, 'render_widget']);
        add_action('rest_api_init', [$this, 'register_rest_routes']);
        add_action('admin_post_heyjarvis_save_settings', [$this, 'save_settings']);
        add_action('admin_post_heyjarvis_test_connection', [$this, 'test_connection']);
    }

    public function init() {
        add_action('admin_post_heyjarvis_save_settings', [$this, 'save_settings']);
        load_plugin_textdomain('heyjarvis-chat', false, dirname(plugin_basename(__FILE__)) . '/languages');
    }

    public function enqueue_scripts() {
        $options = get_option('heyjarvis_chat_options');
        $practice_slug = isset($options['practice_slug']) ? esc_js($options['practice_slug']) : '';

        wp_add_inline_script('heyjarvis-widget', 'window.heyJarvisConfig = { practiceSlug: "' . $practice_slug . '", apiUrl: "' . esc_url(rest_url('heyjarvis/v1')) . '" };', 'before');
        wp_enqueue_script('heyjarvis-widget', HEYJARVIS_PLUGIN_URL . 'assets/js/widget-loader.js', [], HEYJARVIS_VERSION, true);
        wp_enqueue_style('heyjarvis-widget', HEYJARVIS_PLUGIN_URL . 'assets/css/widget.css', [], HEYJARVIS_VERSION);
    }

    public function render_widget() {
        $options = get_option('heyjarvis_chat_options');
        $enabled = isset($options['enabled']) ? $options['enabled'] : true;

        if (!$enabled) return;

        $position = isset($options['position']) ? $options['position'] : 'right';
        $primary_color = isset($options['primary_color']) ? $options['primary_color'] : '#2563eb';
        $greeting = isset($options['greeting']) ? $options['greeting'] : 'Hi! 👋 How can we help you today?';

        include HEYJARVIS_PLUGIN_DIR . 'templates/widget-container.php';
    }

    public function admin_menu() {
        add_options_page(
            'HeyJarvis Chat Settings',
            'HeyJarvis Chat',
            'manage_options',
            'heyjarvis-chat',
            [$this, 'settings_page']
        );
    }

    public function settings_page() {
        if (isset($_POST['_wpnonce']) && wp_verify_nonce($_POST['_wpnonce'], 'heyjarvis_save_settings')) {
            $this->save_settings();
        }
        $options = get_option('heyjarvis_chat_options', []);
        include HEYJARVIS_PLUGIN_DIR . 'templates/settings-page.php';
    }

    public function save_settings() {
        if (!current_user_can('manage_options')) {
            wp_die('Unauthorized');
        }

        if (!wp_verify_nonce($_POST['_wpnonce'] ?? '', 'heyjarvis_save_settings')) {
            wp_die('Security check failed');
        }

        $options = [
            'enabled' => isset($_POST['heyjarvis_enabled']),
            'practice_slug' => sanitize_text_field($_POST['heyjarvis_practice_slug'] ?? ''),
            'position' => sanitize_text_field($_POST['heyjarvis_position'] ?? 'right'),
            'primary_color' => sanitize_hex_color($_POST['heyjarvis_primary_color'] ?? '#2563eb'),
            'greeting' => sanitize_textarea_field($_POST['heyjarvis_greeting'] ?? ''),
            'title' => sanitize_text_field($_POST['heyjarvis_title'] ?? 'Chat with us'),
            'auto_open' => isset($_POST['heyjarvis_auto_open']),
            'auto_open_delay' => intval($_POST['heyjarvis_auto_open_delay'] ?? 5000),
        ];

        update_option('heyjarvis_chat_options', $options);
        wp_redirect(add_query_arg('page', 'heyjarvis-chat', admin_url('options-general.php')) . '&updated=1');
        exit;
    }

    public function test_connection() {
        wp_die('Test connection - implementation pending');
    }

    public function register_rest_routes() {
        register_rest_route('heyjarvis/v1', '/health', [
            'methods' => 'GET',
            'callback' => [$this, 'health_check'],
            'permission_callback' => '__return_true',
        ]);
    }

    public function health_check($request) {
        return new WP_REST_Response(['status' => 'ok', 'version' => HEYJARVIS_VERSION], 200);
    }
}

HeyJarvis_Chat::get_instance();
