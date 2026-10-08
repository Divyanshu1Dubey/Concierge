<?php
/**
 * Plugin Name: HeyJarvis Concierge Widget
 * Plugin URI: https://heyjarvis.com
 * Description: Embed the HeyJarvis AI concierge chat widget on your WordPress site.
 * Version: 1.0.0
 * Author: HeyJarvis
 * Author URI: https://heyjarvis.com
 * License: Proprietary
 * Text Domain: heyjarvis
 */

// Prevent direct access
if (!defined('ABSPATH')) {
    exit;
}

/**
 * Plugin activation hook
 */
function heyjarvis_activate() {
    // Set default options
    $defaults = array(
        'practice_slug' => '',
        'api_url'       => 'https://api.heyjarvis.com',
        'button_color'  => '#2563eb',
        'title'         => 'Chat with us',
        'subtitle'      => 'We typically reply in minutes',
    );

    foreach ($defaults as $key => $value) {
        if (get_option('heyjarvis_' . $key) === false) {
            add_option('heyjarvis_' . $key, $value);
        }
    }

    // Flush rewrite rules if needed in future
    flush_rewrite_rules();
}

/**
 * Plugin deactivation hook
 */
function heyjarvis_deactivate() {
    flush_rewrite_rules();
}

register_activation_hook(__FILE__, 'heyjarvis_activate');
register_deactivation_hook(__FILE__, 'heyjarvis_deactivate');

/**
 * Enqueue the HeyJarvis widget script
 */
function heyjarvis_enqueue_script() {
    // Get settings
    $practice_slug = get_option('heyjarvis_practice_slug', '');
    $api_url       = get_option('heyjarvis_api_url', 'https://api.heyjarvis.com');
    $button_color  = get_option('heyjarvis_button_color', '#2563eb');
    $title         = get_option('heyjarvis_title', 'Chat with us');
    $subtitle      = get_option('heyjarvis_subtitle', 'We typically reply in minutes');

    // Skip if no practice slug configured
    if (empty($practice_slug)) {
        return;
    }

    $widget_url = plugins_url('dist/widget.js', __FILE__);

    // Build data attributes for the script tag
    $data_attrs = array(
        'data-practice-slug'  => esc_attr($practice_slug),
        'data-api-url'        => esc_url($api_url),
        'data-primary-color'  => esc_attr(sanitize_hex_color($button_color)),
        'data-title'          => esc_attr($title),
        'data-subtitle'       => esc_attr($subtitle),
    );

    $data_string = '';
    foreach ($data_attrs as $attr => $value) {
        $data_string .= ' ' . $attr . '="' . $value . '"';
    }

    // Inline the script tag with data attributes
    // This avoids needing a separate JS file for configuration
    ?>
    <script<?php echo $data_string; ?> src="<?php echo esc_url($widget_url); ?>"></script>
    <?php
}

/**
 * Shortcode: [heyjarvis]
 */
function heyjarvis_shortcode($atts) {
    $atts = shortcode_atts(
        array(
            'practice_slug' => get_option('heyjarvis_practice_slug', ''),
            'api_url'       => get_option('heyjarvis_api_url', 'https://api.heyjarvis.com'),
            'button_color'  => get_option('heyjarvis_button_color', '#2563eb'),
            'title'         => get_option('heyjarvis_title', 'Chat with us'),
            'subtitle'      => get_option('heyjarvis_subtitle', 'We typically reply in minutes'),
        ),
        $atts,
        'heyjarvis'
    );

    $practice_slug = sanitize_text_field($atts['practice_slug']);
    if (empty($practice_slug)) {
        return '<!-- HeyJarvis: practice_slug not configured -->';
    }

    $api_url      = esc_url($atts['api_url']);
    $button_color = sanitize_hex_color($atts['button_color']);
    $title        = esc_attr($atts['title']);
    $subtitle     = esc_attr($atts['subtitle']);
    $widget_url   = plugins_url('dist/widget.js', __FILE__);

    $data_attrs = ' data-practice-slug="' . $practice_slug . '"'
                . ' data-api-url="' . $api_url . '"'
                . ' data-primary-color="' . $button_color . '"'
                . ' data-title="' . $title . '"'
                . ' data-subtitle="' . $subtitle . '"';

    return '<script' . $data_attrs . ' src="' . $widget_url . '"></script>';
}

add_shortcode('heyjarvis', 'heyjarvis_shortcode');

/**
 * Register settings
 */
function heyjarvis_register_settings() {
    register_setting('heyjarvis_settings', 'heyjarvis_practice_slug', array(
        'type'              => 'string',
        'sanitize_callback' => 'sanitize_text_field',
        'default'           => '',
    ));

    register_setting('heyjarvis_settings', 'heyjarvis_api_url', array(
        'type'              => 'string',
        'sanitize_callback' => 'esc_url_raw',
        'default'           => 'https://api.heyjarvis.com',
    ));

    register_setting('heyjarvis_settings', 'heyjarvis_button_color', array(
        'type'              => 'string',
        'sanitize_callback' => 'sanitize_hex_color',
        'default'           => '#2563eb',
    ));

    register_setting('heyjarvis_settings', 'heyjarvis_title', array(
        'type'              => 'string',
        'sanitize_callback' => 'sanitize_text_field',
        'default'           => 'Chat with us',
    ));

    register_setting('heyjarvis_settings', 'heyjarvis_subtitle', array(
        'type'              => 'string',
        'sanitize_callback' => 'sanitize_text_field',
        'default'           => 'We typically reply in minutes',
    ));
}

add_action('admin_init', 'heyjarvis_register_settings');

/**
 * Add admin menu
 */
function heyjarvis_add_admin_menu() {
    add_options_page(
        __('HeyJarvis Settings', 'heyjarvis'),
        __('HeyJarvis', 'heyjarvis'),
        'manage_options',
        'heyjarvis',
        'heyjarvis_settings_page'
    );
}

add_action('admin_menu', 'heyjarvis_add_admin_menu');

/**
 * Settings page callback
 */
function heyjarvis_settings_page() {
    ?>
    <div class="wrap">
        <h1><?php echo esc_html__('HeyJarvis Concierge Widget', 'heyjarvis'); ?></h1>
        <p><?php echo esc_html__('Configure the HeyJarvis AI chat widget for your website.', 'heyjarvis'); ?></p>

        <?php if (isset($_GET['settings-updated'])) : ?>
            <div class="notice notice-success is-dismissible">
                <p><?php echo esc_html__('Settings saved successfully.', 'heyjarvis'); ?></p>
            </div>
        <?php endif; ?>

        <form method="post" action="options.php">
            <?php
            settings_fields('heyjarvis_settings');
            do_settings_sections('heyjarvis_settings');
            ?>

            <table class="form-table">
                <tr>
                    <th scope="row">
                        <label for="heyjarvis_practice_slug">
                            <?php echo esc_html__('Practice Slug', 'heyjarvis'); ?>
                        </label>
                    </th>
                    <td>
                        <input
                            type="text"
                            id="heyjarvis_practice_slug"
                            name="heyjarvis_practice_slug"
                            value="<?php echo esc_attr(get_option('heyjarvis_practice_slug', '')); ?>"
                            class="regular-text"
                            required
                        />
                        <p class="description">
                            <?php echo esc_html__('The unique slug for your practice. This is required for the widget to work.', 'heyjarvis'); ?>
                        </p>
                    </td>
                </tr>

                <tr>
                    <th scope="row">
                        <label for="heyjarvis_api_url">
                            <?php echo esc_html__('API URL', 'heyjarvis'); ?>
                        </label>
                    </th>
                    <td>
                        <input
                            type="url"
                            id="heyjarvis_api_url"
                            name="heyjarvis_api_url"
                            value="<?php echo esc_attr(get_option('heyjarvis_api_url', 'https://api.heyjarvis.com')); ?>"
                            class="regular-text"
                        />
                        <p class="description">
                            <?php echo esc_html__('The base URL of your HeyJarvis API instance.', 'heyjarvis'); ?>
                        </p>
                    </td>
                </tr>

                <tr>
                    <th scope="row">
                        <label for="heyjarvis_button_color">
                            <?php echo esc_html__('Button Color', 'heyjarvis'); ?>
                        </label>
                    </th>
                    <td>
                        <input
                            type="text"
                            id="heyjarvis_button_color"
                            name="heyjarvis_button_color"
                            value="<?php echo esc_attr(get_option('heyjarvis_button_color', '#2563eb')); ?>"
                            class="regular-text"
                            data-spectrum-color
                        />
                        <p class="description">
                            <?php echo esc_html__('The primary color for the chat button and header (hex format).', 'heyjarvis'); ?>
                        </p>
                    </td>
                </tr>

                <tr>
                    <th scope="row">
                        <label for="heyjarvis_title">
                            <?php echo esc_html__('Widget Title', 'heyjarvis'); ?>
                        </label>
                    </th>
                    <td>
                        <input
                            type="text"
                            id="heyjarvis_title"
                            name="heyjarvis_title"
                            value="<?php echo esc_attr(get_option('heyjarvis_title', 'Chat with us')); ?>"
                            class="regular-text"
                        />
                    </td>
                </tr>

                <tr>
                    <th scope="row">
                        <label for="heyjarvis_subtitle">
                            <?php echo esc_html__('Widget Subtitle', 'heyjarvis'); ?>
                        </label>
                    </th>
                    <td>
                        <input
                            type="text"
                            id="heyjarvis_subtitle"
                            name="heyjarvis_subtitle"
                            value="<?php echo esc_attr(get_option('heyjarvis_subtitle', 'We typically reply in minutes')); ?>"
                            class="regular-text"
                        />
                    </td>
                </tr>
            </table>

            <?php submit_button(); ?>
        </form>

        <hr />

        <h2><?php echo esc_html__('Usage', 'heyjarvis'); ?></h2>

        <h3><?php echo esc_html__('Shortcode', 'heyjarvis'); ?></h3>
        <p><?php echo esc_html__('Add the widget to any post or page using the shortcode:', 'heyjarvis'); ?></p>
        <code>[heyjarvis]</code>

        <h3><?php echo esc_html__('Automatic', 'heyjarvis'); ?></h3>
        <p><?php echo esc_html__('The widget will automatically appear on all pages once configured.', 'heyjarvis'); ?></p>

        <h3><?php echo esc_html__('Gutenberg Block', 'heyjarvis'); ?></h3>
        <p><?php echo esc_html__('Use the shortcode block with <code>[heyjarvis]</code> in the Gutenberg editor.', 'heyjarvis'); ?></p>
    </div>
    <?php
}

/**
 * Enqueue admin assets
 */
function heyjarvis_admin_assets($hook) {
    if ($hook !== 'settings_page_heyjarvis') {
        return;
    }

    // Enqueue WordPress color picker styles if available
    wp_enqueue_style('wp-color-picker');
}

add_action('admin_enqueue_scripts', 'heyjarvis_admin_assets');
