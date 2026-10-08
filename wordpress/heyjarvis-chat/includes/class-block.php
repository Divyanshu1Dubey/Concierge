<?php
/**
 * HeyJarvis Chat Gutenberg Block
 *
 * @package HeyJarvis_Chat
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * HeyJarvis_Block class.
 */
class HeyJarvis_Block {

	/**
	 * Constructor — register block assets and the block itself.
	 */
	public function __construct() {
		add_action( 'init', array( $this, 'register_block' ) );
	}

	/**
	 * Register the Gutenberg block.
	 */
	public function register_block() {
		if ( ! function_exists( 'register_block_type' ) ) {
			return;
		}

		$settings = get_option( 'heyjarvis_settings', array() );

		register_block_type(
			'heyjarvis/chat',
			array(
				'attributes'      => array(
					'practiceId'     => array(
						'type'    => 'string',
						'default' => $settings['practice_id'] ?? '',
					),
					'title'          => array(
						'type'    => 'string',
						'default' => $settings['widget_title'] ?? '',
					),
					'subtitle'       => array(
						'type'    => 'string',
						'default' => $settings['subtitle'] ?? '',
					),
					'primaryColor'   => array(
						'type'    => 'string',
						'default' => $settings['primary_color'] ?? '#2563eb',
					),
					'welcomeMessage' => array(
						'type'    => 'string',
						'default' => $settings['welcome_message'] ?? '',
					),
				),
				'render_callback' => array( $this, 'render' ),
				'category'        => 'widgets',
				'icon'            => 'smiley',
				'description'     => __( 'Embed the HeyJarvis AI Dental Concierge chat widget.', 'heyjarvis-chat' ),
				'editor_script'   => 'heyjarvis-block-editor',
				'editor_style'    => 'heyjarvis-block-editor',
			)
		);

		// Register editor assets.
		wp_register_script(
			'heyjarvis-block-editor',
			plugins_url( 'admin/js/admin.js', HEYJARVIS_PLUGIN_FILE ),
			array( 'wp-blocks', 'wp-element', 'wp-editor', 'wp-components' ),
			filemtime( plugin_dir_path( HEYJARVIS_PLUGIN_FILE ) . 'admin/js/admin.js' ),
			true
		);

		wp_register_style(
			'heyjarvis-block-editor',
			plugins_url( 'admin/css/admin.css', HEYJARVIS_PLUGIN_FILE ),
			array( 'wp-edit-blocks' ),
			filemtime( plugin_dir_path( HEYJARVIS_PLUGIN_FILE ) . 'admin/css/admin.css' )
		);
	}

	/**
	 * Render callback for the block.
	 *
	 * @param array $attributes Block attributes.
	 * @return string HTML output.
	 */
	public function render( $attributes ) {
		$practice_id = ! empty( $attributes['practiceId'] ) ? $attributes['practiceId'] : '';

		if ( empty( $practice_id ) ) {
			return '<p class="heyjarvis-error">' . esc_html__( 'HeyJarvis: Please configure a Practice ID in the block settings.', 'heyjarvis-chat' ) . '</p>';
		}

		$atts = array(
			'practice_id'     => sanitize_text_field( $practice_id ),
			'title'           => sanitize_text_field( $attributes['title'] ?? '' ),
			'subtitle'        => sanitize_text_field( $attributes['subtitle'] ?? '' ),
			'primary_color'   => sanitize_hex_color( $attributes['primaryColor'] ?? '#2563eb' ),
			'welcome_message' => sanitize_textarea_field( $attributes['welcomeMessage'] ?? '' ),
		);

		ob_start();
		heyjarvis_chat_render_embed( $atts );
		return ob_get_clean();
	}
}
