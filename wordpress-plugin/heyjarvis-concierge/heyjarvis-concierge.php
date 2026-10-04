<?php
/**
 * Plugin Name: HeyJarvis Concierge
 * Plugin URI: https://heyjarvis.ai
 * Description: Embed the HeyJarvis AI Concierge chat widget on your WordPress site. Collect leads, schedule appointments, and automate front-desk requests.
 * Version: 1.0.0
 * Author: HeyJarvis
 * Author URI: https://heyjarvis.ai
 * License: MIT
 * Text Domain: heyjarvis-concierge
 *
 * @package HeyJarvis\Concierge
 */

// Prevent direct access.
if (!defined('ABSPATH')) {
    exit;
}

define('HEYJARVIS_CONCIERGE_VERSION', '1.0.0');
define('HEYJARVIS_CONCIERGE_PLUGIN_DIR', plugin_dir_path(__FILE__));
define('HEYJARVIS_CONCIERGE_PLUGIN_URL', plugin_dir_url(__FILE__));

/**
 * Class HeyJarvis_Concierge
 */
class HeyJarvis_Concierge {

    /**
     * Plugin instance.
     *
     * @var HeyJarvis_Concierge|null
     */
    private static ?HeyJarvis_Concierge $instance = null;

    /**
     * Get the singleton instance.
     */
    public static function instance(): HeyJarvis_Concierge {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    /**
     * Constructor.
     */
    private function __construct() {
        add_action('admin_menu', [$this, 'add_admin_menu']);
        add_action('admin_init', [$this, 'register_settings']);
        add_action('wp_enqueue_scripts', [$this, 'enqueue_scripts']);
        add_action('wp_footer', [$this, 'render_widget'], 999);
        add_action('wp_head', [$this, 'render_dns_prefetch']);
        register_activation_hook(__FILE__, [$this, 'activate']);
        register_deactivation_hook(__FILE__, [$this, 'deactivate']);
    }

    /**
     * Plugin activation.
     */
    public function activate(): void {
        $defaults = [
            'heyjarvis_client_key' => '',
            'heyjarvis_enabled' => 'yes',
            'heyjarvis_form_mode' => 'no',
            'heyjarvis_auto_open' => 'no',
            'heyjarvis_page_exclusions' => '',
        ];
        foreach ($defaults as $key => $value) {
            if (false === get_option($key)) {
                add_option($key, $value);
            }
        }
        // Flush rewrite rules if we add any custom endpoints.
        flush_rewrite_rules();
    }

    /**
     * Plugin deactivation.
     */
    public function deactivate(): void {
        flush_rewrite_rules();
    }

    /**
     * Add admin menu under Settings.
     */
    public function add_admin_menu(): void {
        add_options_page(
            __('HeyJarvis Concierge', 'heyjarvis-concierge'),
            __('HeyJarvis Concierge', 'heyjarvis-concierge'),
            'manage_options',
            'heyjarvis-concierge',
            [$this, 'render_settings_page']
        );
    }

    /**
     * Register plugin settings.
     */
    public function register_settings(): void {
        register_setting('heyjarvis_concierge_options', 'heyjarvis_client_key', [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => '',
        ]);
        register_setting('heyjarvis_concierge_options', 'heyjarvis_enabled', [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => 'yes',
        ]);
        register_setting('heyjarvis_concierge_options', 'heyjarvis_form_mode', [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => 'no',
        ]);
        register_setting('heyjarvis_concierge_options', 'heyjarvis_auto_open', [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => 'no',
        ]);
        register_setting('heyjarvis_concierge_options', 'heyjarvis_page_exclusions', [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_textarea_field',
            'default' => '',
        ]);
        register_setting('heyjarvis_concierge_options', 'heyjarvis_widget_url', [
            'type' => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default' => 'https://app.heyjarvis.ai/widget.js',
        ]);
    }

    /**
     * Get the widget JS URL.
     */
    private function get_widget_url(): string {
        return get_option('heyjarvis_widget_url', 'https://app.heyjarvis.ai/widget.js');
    }

    /**
     * Get the public client key.
     */
    private function get_client_key(): string {
        return get_option('heyjarvis_client_key', '');
    }

    /**
     * Check if widget should load on current page.
     */
    private function should_load_on_current_page(): bool {
        // Check if enabled globally.
        if ('yes' !== get_option('heyjarvis_enabled', 'yes')) {
            return false;
        }

        // Check page exclusions.
        $exclusions = get_option('heyjarvis_page_exclusions', '');
        if (empty($exclusions)) {
            return true;
        }

        $excluded_paths = array_map('trim', explode("\n", $exclusions));
        $current_path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?? '/';

        foreach ($excluded_paths as $path) {
            if (empty($path)) {
                continue;
            }
            // Support glob patterns.
            if (str_contains($path, '*')) {
                $pattern = str_replace('\*', '.*', preg_quote($path, '/'));
                if (preg_match('#^' . $pattern . '$#', $current_path)) {
                    return false;
                }
            } elseif ($path === $current_path || str_starts_with($current_path, $path)) {
                return false;
            }
        }

        return true;
    }

    /**
     * Render settings page.
     */
    public function render_settings_page(): void {
        if (!current_user_can('manage_options')) {
            return;
        }
        $client_key = get_option('heyjarvis_client_key', '');
        $enabled = get_option('heyjarvis_enabled', 'yes') === 'yes';
        $widget_url = $this->get_widget_url();
        ?>
        <div class="wrap">
            <h1>HeyJarvis Concierge</h1>
            <p>
                Embed your AI Concierge widget on your WordPress site.
                Get your public client key from your
                <a href="https://app.heyjarvis.ai" target="_blank">HeyJarvis dashboard</a>.
            </p>

            <?php if (empty($client_key)) : ?>
                <div class="notice notice-warning inline">
                    <p><strong>Setup required:</strong> Enter your public client key below to activate the widget.</p>
                </div>
            <?php endif; ?>

            <?php if ($enabled && !empty($client_key)) : ?>
                <div class="notice notice-success inline">
                    <p><strong>Connected:</strong> Your HeyJarvis Concierge is active on your site.
                        <a href="https://app.heyjarvis.ai/concierge/<?php echo esc_attr($this->get_tenant_slug()); ?>" target="_blank">Test it here</a>.
                    </p>
                </div>
            <?php endif; ?>

            <form method="post" action="options.php">
                <?php settings_fields('heyjarvis_concierge_options'); ?>
                <table class="form-table" role="presentation">
                    <tr>
                        <th scope="row">
                            <label for="heyjarvis_client_key">Public Client Key</label>
                        </th>
                        <td>
                            <input name="heyjarvis_client_key" type="text" id="heyjarvis_client_key"
                                   value="<?php echo esc_attr(get_option('heyjarvis_client_key', '')); ?>"
                                   class="regular-text"
                                   placeholder="pk_...">
                            <p class="description">
                                Find this in your HeyJarvis dashboard under <em>Installation</em>.
                                Safe to use in public code.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">
                            <label for="heyjarvis_widget_url">Widget Script URL</label>
                        </th>
                        <td>
                            <input name="heyjarvis_widget_url" type="text" id="heyjarvis_widget_url"
                                   value="<?php echo esc_attr($widget_url); ?>"
                                   class="regular-text">
                            <p class="description">
                                Override only if you are self-hosting the widget script.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">
                            <label for="heyjarvis_enabled">Enable Widget</label>
                        </th>
                        <td>
                            <select name="heyjarvis_enabled" id="heyjarvis_enabled">
                                <option value="yes" <?php selected(get_option('heyjarvis_enabled', 'yes'), 'yes'); ?>>Yes, site-wide</option>
                                <option value="no" <?php selected(get_option('heyjarvis_enabled', 'yes'), 'no'); ?>>No, disable for now</option>
                            </select>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">
                            <label for="heyjarvis_form_mode">Form Mode</label>
                        </th>
                        <td>
                            <select name="heyjarvis_form_mode" id="heyjarvis_form_mode">
                                <option value="no" <?php selected(get_option('heyjarvis_form_mode', 'no'), 'no'); ?>>Conversational (default)</option>
                                <option value="yes" <?php selected(get_option('heyjarvis_form_mode', 'no'), 'yes'); ?>>Form Mode</option>
                            </select>
                            <p class="description">Use traditional form layout instead of chat conversation.</p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">
                            <label for="heyjarvis_auto_open">Auto-Open</label>
                        </th>
                        <td>
                            <select name="heyjarvis_auto_open" id="heyjarvis_auto_open">
                                <option value="no" <?php selected(get_option('heyjarvis_auto_open', 'no'), 'no'); ?>>No (visitor clicks to open)</option>
                                <option value="yes" <?php selected(get_option('heyjarvis_auto_open', 'no'), 'yes'); ?>>Yes (open automatically)</option>
                            </select>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">
                            <label for="heyjarvis_page_exclusions">Page Exclusions</label>
                        </th>
                        <td>
                            <textarea name="heyjarvis_page_exclusions" id="heyjarvis_page_exclusions"
                                      rows="5" class="large-text code"
                                      placeholder="/checkout/&#10;/admin/&#10;/wp-login.php"><?php echo esc_textarea(get_option('heyjarvis_page_exclusions', '')); ?></textarea>
                            <p class="description">
                                One URL path per line. Supports glob patterns (e.g. <code>/checkout/*</code>).
                                The widget will NOT appear on these pages.
                            </p>
                        </td>
                    </tr>
                </table>
                <?php submit_button(__('Save Settings', 'heyjarvis-concierge')); ?>
            </form>

            <hr>
            <h2>Manual Installation</h2>
            <p>If you prefer to add the widget manually, paste this into your theme's <code>footer.php</code> or use a Custom HTML widget:</p>
            <textarea readonly rows="3" class="large-text code" id="manual-snippet">
<script src="<?php echo esc_url($widget_url); ?>" data-heyjarvis-client="<?php echo esc_attr($client_key); ?>" async></script></textarea>
            <button class="button" onclick="navigator.clipboard.writeText(document.getElementById('manual-snippet').value);alert('Copied!')">Copy Snippet</button>
            <br><br>
            <p class="description">
                <strong>Note:</strong> Your public client key (<code>pk_...</code>) is safe to expose in page source.
                Never share your secret API key.
            </p>
        </div>
        <?php
    }

    /**
     * Enqueue plugin scripts/styles.
     */
    public function enqueue_scripts(): void {
        // No inline styles needed — widget is fully isolated.
        // This hook exists for future asset management.
    }

    /**
     * Render DNS prefetch hints.
     */
    public function render_dns_prefetch(): void {
        $widget_url = $this->get_widget_url();
        $host = wp_parse_url($widget_url, PHP_URL_HOST);
        if ($host) {
            echo '<link rel="dns-prefetch" href="//' . esc_url($host) . '">' . "\n";
        }
    }

    /**
     * Render the widget script tag in the footer.
     */
    public function render_widget(): void {
        if (!$this->should_load_on_current_page()) {
            return;
        }

        $client_key = $this->get_client_key();
        if (empty($client_key)) {
            // Only log in debug mode to avoid spamming production logs.
            if (defined('WP_DEBUG') && WP_DEBUG) {
                error_log('[HeyJarvis] Client key not configured.');
            }
            return;
        }

        $widget_url = $this->get_widget_url();
        $form_mode = get_option('heyjarvis_form_mode', 'no') === 'yes' ? 'true' : 'false';
        $auto_open = get_option('heyjarvis_auto_open', 'no') === 'yes' ? 'true' : 'false';

        // Build data attributes.
        $attrs = [
            'src' => esc_url($widget_url),
            'data-heyjarvis-client' => esc_attr($client_key),
            'data-heyjarvis-form' => $form_mode,
            'data-heyjarvis-auto-open' => $auto_open,
            'async',
        ];

        printf(
            '<script %s></script>' . "\n",
            implode(' ', array_map(
                fn($k, $v) => $k === 'src' || $k === 'async'
                    ? sprintf('%s="%s"', $k, $v)
                    : sprintf('%s="%s"', $k, $v),
                array_keys($attrs),
                array_values($attrs)
            ))
        );
    }

    /**
     * Derive a tenant slug from the client key.
     * Used for constructing hosted concierge URLs.
     */
    private function get_tenant_slug(): string {
        $key = $this->get_client_key();
        // Generate a stable slug from the key for the hosted link.
        // In practice, the tenant slug comes from the HeyJarvis dashboard.
        return 'my-business';
    }
}

// Initialize plugin.
HeyJarvis_Concierge::instance();
