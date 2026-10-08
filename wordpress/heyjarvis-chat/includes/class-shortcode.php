<?php
/**
 * HeyJarvis Chat Shortcode
 *
 * @package HeyJarvis_Chat
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * HeyJarvis_Shortcode class.
 */
class HeyJarvis_Shortcode {

	/**
	 * Constructor — register the shortcode.
	 */
	public function __construct() {
		add_shortcode( 'heyjarvis_chat', array( $this, 'render' ) );
	}

	/**
	 * Shortcode render callback.
	 *
	 * @param array  $atts    Shortcode attributes.
	 * @param string $content Shortcode content (not used).
	 * @return string HTML output.
	 */
	public function render( $atts, $content = '' ) {
		$settings = get_option( 'heyjarvis_settings', array() );

		$atts = shortcode_atts(
			array(
				'practice_id'     => $settings['practice_id'] ?? '',
				'title'           => $settings['widget_title'] ?? '',
				'subtitle'        => $settings['subtitle'] ?? '',
				'welcome_message' => $settings['welcome_message'] ?? '',
				'primary_color'   => $settings['primary_color'] ?? '#2563eb',
			),
			$atts,
			'heyjarvis_chat'
		);

		if ( empty( $atts['practice_id'] ) ) {
			return '<p class="heyjarvis-error">' . esc_html__( 'HeyJarvis: Practice ID is not configured.', 'heyjarvis-chat' ) . '</p>';
		}

		// Sanitize attributes.
		$atts['practice_id']     = sanitize_text_field( $atts['practice_id'] );
		$atts['title']           = sanitize_text_field( $atts['title'] );
		$atts['subtitle']        = sanitize_text_field( $atts['subtitle'] );
		$atts['welcome_message'] = sanitize_textarea_field( $atts['welcome_message'] );
		$atts['primary_color']   = sanitize_hex_color( $atts['primary_color'] );

		ob_start();
		heyjarvis_chat_render_embed( $atts );
		return ob_get_clean();
	}
}
