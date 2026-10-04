<?php
/**
 * Plugin Name: HeyJarvis Concierge
 * Plugin URI: https://heyjarvis.ai
 * Description: AI-powered front desk assistant for appointment-based businesses.
 * Version: 1.0.0
 * Author: HeyJarvis
 * Author URI: https://heyjarvis.ai
 * License: Proprietary
 * Text Domain: heyjarvis-concierge
 */

if (!defined('ABSPATH')) exit;

class HeyJarvis_Concierge {

    const OPTION_KEY = 'heyjarvis_concierge_settings';
    const DEFAULT_CLIENT_KEY = '';

    public function __construct() {
        add_action('admin_menu', [$this, 'add_admin_menu']);
        add_action('admin_init', [$this, 'register_settings']);
        add_action('wp_enqueue_scripts', [$this, 'enqueue_widget']);
        add_action('wp_footer', [$this, 'inject_widget']);
        add_action('wp_ajax_heyjarvis_test', [$this, 'ajax_test']);
        add_action('wp_ajax_nopriv_heyjarvis_test', [$this, 'ajax_test']);
    }

    public function add_admin_menu(): void {
        add_options_page(
            'HeyJarvis Concierge',
            'HeyJarvis Concierge',
            'manage_options',
            'heyjarvis-concierge',
            [$this, 'render_settings_page']
        );
    }

    public function register_settings(): void {
        register_setting(self::OPTION_KEY, 'client_key', [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default' => '',
        ]);
        register_setting(self::OPTION_KEY, 'enabled', [
            'type' => 'boolean',
            'sanitize_callback' => [$this, 'sanitize_bool'],
            'default' => false,
        ]);
        register_setting(self::OPTION_KEY, 'auto_open', [
            'type' => 'boolean',
            'sanitize_callback' => [$this, 'sanitize_bool'],
            'default' => false,
        ]);
        register_setting(self::OPTION_KEY, 'form_mode', [
            'type' => 'boolean',
            'sanitize_callback' => [$this, 'sanitize_bool'],
            'default' => false,
        ]);
        register_setting(self::OPTION_KEY, 'excluded_pages', [
            'type' => 'string',
            'sanitize_callback' => 'sanitize_textarea_field',
            'default' => '',
        ]);
        register_setting(self::OPTION_KEY, 'app_url', [
            'type' => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default' => 'https://app.heyjarvis.ai',
        ]);
    }

    public function sanitize_bool($value): bool {
        return (bool) $value;
    }

    public function get_settings(): array {
        $defaults = [
            'client_key' => '',
            'enabled' => false,
            'auto_open' => false,
            'form_mode' => false,
            'excluded_pages' => '',
            'app_url' => 'https://app.heyjarvis.ai',
        ];
        return wp_parse_args(get_option(self::OPTION_KEY, []), $defaults);
    }

    public function is_enabled(): bool {
        $settings = $this->get_settings();
        if (empty($settings['client_key']) || !$settings['enabled']) {
            return false;
        }
        // Check excluded pages
        $excluded = array_filter(array_map('trim', explode("\n", $settings['excluded_pages'])));
        if (!empty($excluded)) {
            $slug = sanitize_title(get_post_field('post_name', get_queried_object_id()));
            $path = trim(parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH), '/');
            foreach ($excluded as $page) {
                if ($slug === sanitize_title($page) || $path === $page || str_starts_with($path, $page . '/')) {
                    return false;
                }
            }
        }
        return true;
    }

    public function inject_widget(): void {
        if (!$this->is_enabled()) return;
        $settings = $this->get_settings();
        $client_key = esc_attr($settings['client_key']);
        $app_url = esc_url(rtrim($settings['app_url'], '/'));
        $form_attr = $settings['form_mode'] ? ' data-heyjarvis-form="true"' : '';
        $auto_open = $settings['auto_open'] ? ' data-heyjarvis-auto-open="true"' : '';
        ?>
<script
  src="<?php echo $app_url; ?>/widget.js"
  data-heyjarvis-client="<?php echo $client_key; ?>"
  async
  id="heyjarvis-widget-script"
  <?php echo $form_attr; ?>
  <?php echo $auto_open; ?>
></script>
        <?php
    }

    public function enqueue_widget(): void {
        // CSS for widget container (minimal)
        wp_add_inline_style('wp-block-template-part', '.heyjarvis-widget-container { position: fixed; bottom: 0; right: 0; z-index: 99999; }');
    }

    public function render_settings_page(): void {
        if (!current_user_can('manage_options')) return;
        $settings = $this->get_settings();
        $connection_status = $this->check_connection($settings);
        ?>
        <div class="wrap">
            <h1>HeyJarvis Concierge</h1>
            <p>Configure your AI front-desk assistant. Get your <a href="https://app.heyjarvis.ai" target="_blank">Client Key</a> from your HeyJarvis dashboard.</p>

            <form method="post" action="options.php">
                <?php settings_fields(self::OPTION_KEY); ?>
                <?php do_settings_sections(self::OPTION_KEY); ?>

                <table class="form-table">
                    <tr>
                        <th scope="row">Status</th>
                        <td>
                            <strong style="color: <?php echo $connection_status['connected'] ? 'green' : 'orange'; ?>;">
                                <?php echo $connection_status['connected'] ? '&#10003; Connected' : '&#9679; Not Connected'; ?>
                            </strong>
                            <p class="description"><?php echo esc_html($connection_status['message']); ?></p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">Client Key</th>
                        <td>
                            <input type="text" name="heyjarvis_concierge_settings[client_key]"
                                   value="<?php echo esc_attr($settings['client_key']); ?>"
                                   class="regular-text" placeholder="hj_live_xxxxxxxxx" />
                            <p class="description">Your public API key from the HeyJarvis dashboard.</p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">App URL</th>
                        <td>
                            <input type="url" name="heyjarvis_concierge_settings[app_url]"
                                   value="<?php echo esc_attr($settings['app_url']); ?>"
                                   class="regular-text" />
                            <p class="description">Your HeyJarvis app domain.</p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">Enable Concierge</th>
                        <td>
                            <label>
                                <input type="checkbox" name="heyjarvis_concierge_settings[enabled]"
                                       value="1" <?php checked($settings['enabled'], true); ?> />
                                Show Concierge widget on this site
                            </label>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">Auto-Open</th>
                        <td>
                            <label>
                                <input type="checkbox" name="heyjarvis_concierge_settings[auto_open]"
                                       value="1" <?php checked($settings['auto_open'], true); ?> />
                                Automatically open the widget for visitors
                            </label>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">Form Mode</th>
                        <td>
                            <label>
                                <input type="checkbox" name="heyjarvis_concierge_settings[form_mode]"
                                       value="1" <?php checked($settings['form_mode'], true); ?> />
                                Use structured form instead of conversational mode
                            </label>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row">Excluded Pages</th>
                        <td>
                            <textarea name="heyjarvis_concierge_settings[excluded_pages]"
                                      rows="4" class="large-text"
                                      placeholder="One page slug or path per line"><?php echo esc_textarea($settings['excluded_pages']); ?></textarea>
                            <p class="description">One page slug or URL path per line. The widget will not appear on these pages.</p>
                        </td>
                    </tr>
                </table>

                <?php submit_button(); ?>
            </form>

            <hr />
            <h2>Installation Complete</h2>
            <p>Once saved, the Concierge widget will load on your website.</p>
            <p><strong>No code editing required.</strong> The plugin automatically injects the widget script.</p>
        </div>
        <?php
    }

    private function check_connection(array $settings): array {
        if (empty($settings['client_key'])) {
            return ['connected' => false, 'message' => 'No client key configured. Add your key above.'];
        }
        if (empty($settings['enabled'])) {
            return ['connected' => false, 'message' => 'Concierge is disabled. Enable it above.'];
        }
        return ['connected' => true, 'message' => 'Widget is active and will appear on your site.'];
    }

    public function ajax_test(): void {
        header('Content-Type: application/json');
        $settings = $this->get_settings();
        echo json_encode([
            'enabled' => $this->is_enabled(),
            'client_key' => !empty($settings['client_key']),
            'app_url' => $settings['app_url'],
        ]);
        wp_die();
    }
}

new HeyJarvis_Concierge();
