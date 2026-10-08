<?php
/**
 * Plugin Name: HeyJarvis AI Chat
 * Plugin URI: https://heyjarvis.com
 * Description: Embed the HeyJarvis AI Dental Concierge chat widget on your WordPress website.
 * Version: 1.0.0
 * Author: HeyJarvis
 * License: MIT
 */

if (!defined('ABSPATH')) {
    exit;
}

class HeyJarvis_Chat {

    const OPTION_GROUP = 'heyjarvis_chat_options';
    const OPTION_NAME  = 'heyjarvis_chat';

    public function __construct() {
        add_action('admin_menu', [$this, 'add_admin_menu']);
        add_action('admin_init', [$this, 'register_settings']);
        add_action('wp_footer', [$this, 'render_widget']);
    }

    public function add_admin_menu(): void {
        add_options_page(
            'HeyJarvis Chat Settings',
            'HeyJarvis Chat',
            'manage_options',
            'heyjarvis-chat',
            [$this, 'render_admin_page']
        );
    }

    public function register_settings(): void {
        register_setting(self::OPTION_GROUP, self::OPTION_NAME, [
            'type'              => 'array',
            'sanitize_callback' => [$this, 'sanitize_options'],
            'default'           => [
                'practice_slug'  => '',
                'api_url'        => '',
                'primary_color'  => '#2563eb',
                'title'          => 'Chat with us',
                'subtitle'       => "We're here to help you schedule an appointment.",
                'greeting'       => 'Hello! How can I help you today?',
                'placeholder'    => 'Type your message...',
                'enabled'        => false,
            ],
        ]);
    }

    public function sanitize_options($input): array {
        $sanitized = [];
        $allowed_colors = ['#2563eb', '#059669', '#dc2626', '#7c3aed', '#ea580c', '#0891b2'];
        $default_color = '#2563eb';

        $sanitized['practice_slug'] = sanitize_text_field($input['practice_slug'] ?? '');
        $sanitized['api_url']       = esc_url_raw($input['api_url'] ?? '');
        $sanitized['primary_color']  = in_array($input['primary_color'], $allowed_colors, true)
            ? $input['primary_color']
            : $default_color;
        $sanitized['title']       = sanitize_text_field($input['title'] ?? 'Chat with us');
        $sanitized['subtitle']    = sanitize_textarea_field($input['subtitle'] ?? '');
        $sanitized['greeting']    = sanitize_textarea_field($input['greeting'] ?? '');
        $sanitized['placeholder'] = sanitize_text_field($input['placeholder'] ?? 'Type your message...');
        $sanitized['enabled']     = !empty($input['enabled']);

        return $sanitized;
    }

    public function render_admin_page(): void {
        $options = get_option(self::OPTION_NAME);
        ?>
        <div class="wrap">
            <h1>HeyJarvis AI Chat</h1>
            <p>Configure the HeyJarvis chat widget for your website.</p>
            <form method="post" action="options.php">
                <?php settings_fields(self::OPTION_GROUP); ?>
                <table class="form-table">
                    <tr>
                        <th scope="row">Enable Widget</th>
                        <td>
                            <label>
                                <input type="checkbox" name="<?php echo esc_attr(self::OPTION_NAME); ?>[enabled]" value="1" <?php checked($options['enabled'] ?? false, true); ?> />
                                Show chat widget on all pages
                            </label>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="practice_slug">Practice Slug</label></th>
                        <td>
                            <input type="text" id="practice_slug" name="<?php echo esc_attr(self::OPTION_NAME); ?>[practice_slug]" value="<?php echo esc_attr($options['practice_slug'] ?? ''); ?>" class="regular-text" />
                            <p class="description">Your HeyJarvis practice slug (e.g., raleigh-dentistry)</p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="api_url">API URL</label></th>
                        <td>
                            <input type="url" id="api_url" name="<?php echo esc_attr(self::OPTION_NAME); ?>[api_url]" value="<?php echo esc_attr($options['api_url'] ?? ''); ?>" class="regular-text" />
                            <p class="description">Your HeyJarvis API URL (e.g., https://api.heyjarvis.com)</p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="primary_color">Primary Color</label></th>
                        <td>
                            <select id="primary_color" name="<?php echo esc_attr(self::OPTION_NAME); ?>[primary_color]">
                                <option value="#2563eb" <?php selected($options['primary_color'] ?? '', '#2563eb'); ?>>Blue</option>
                                <option value="#059669" <?php selected($options['primary_color'] ?? '', '#059669'); ?>>Green</option>
                                <option value="#dc2626" <?php selected($options['primary_color'] ?? '', '#dc2626'); ?>>Red</option>
                                <option value="#7c3aed" <?php selected($options['primary_color'] ?? '', '#7c3aed'); ?>>Purple</option>
                                <option value="#ea580c" <?php selected($options['primary_color'] ?? '', '#ea580c'); ?>>Orange</option>
                                <option value="#0891b2" <?php selected($options['primary_color'] ?? '', '#0891b2'); ?>>Cyan</option>
                            </select>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="title">Widget Title</label></th>
                        <td><input type="text" id="title" name="<?php echo esc_attr(self::OPTION_NAME); ?>[title]" value="<?php echo esc_attr($options['title'] ?? ''); ?>" class="regular-text" /></td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="subtitle">Subtitle</label></th>
                        <td><input type="text" id="subtitle" name="<?php echo esc_attr(self::OPTION_NAME); ?>[subtitle]" value="<?php echo esc_attr($options['subtitle'] ?? ''); ?>" class="regular-text" /></td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="greeting">Greeting Message</label></th>
                        <td><textarea id="greeting" name="<?php echo esc_attr(self::OPTION_NAME); ?>[greeting]" rows="3" class="large-text"><?php echo esc_textarea($options['greeting'] ?? ''); ?></textarea></td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="placeholder">Input Placeholder</label></th>
                        <td><input type="text" id="placeholder" name="<?php echo esc_attr(self::OPTION_NAME); ?>[placeholder]" value="<?php echo esc_attr($options['placeholder'] ?? ''); ?>" class="regular-text" /></td>
                    </tr>
                </table>
                <?php submit_button(); ?>
            </form>
        </div>
        <?php
    }

    public function render_widget(): void {
        $options = get_option(self::OPTION_NAME);

        if (empty($options['enabled']) || empty($options['practice_slug'])) {
            return;
        }

        $practiceSlug  = esc_js($options['practice_slug']);
        $apiUrl        = esc_js($options['api_url'] ?: home_url('/'));
        $primaryColor  = esc_js($options['primary_color']);
        $title         = esc_js($options['title']);
        $subtitle      = esc_js($options['subtitle']);
        $greeting      = esc_js($options['greeting']);
        $placeholder   = esc_js($options['placeholder']);

        ?>
        <script>
        (function(){
            var c=document.createElement('script');
            c.async=true;
            c.src='<?php echo esc_url($apiUrl); ?>/widget/embed.js';
            c.setAttribute('data-practice','<?php echo $practiceSlug; ?>');
            c.setAttribute('data-api-url','<?php echo $apiUrl; ?>');
            c.setAttribute('data-primary-color','<?php echo $primaryColor; ?>');
            var s=document.getElementsByTagName('script')[0];
            s.parentNode.insertBefore(c,s);
        })();
        </script>
        <?php
    }
}

new HeyJarvis_Chat();
