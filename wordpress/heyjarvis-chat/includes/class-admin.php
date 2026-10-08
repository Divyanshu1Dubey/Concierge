<?php
/**
 * Admin settings page handler.
 *
 * @package HeyJarvis_Chat
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Admin settings class.
 */
class HeyJarvis_Chat_Admin {

	/**
	 * Option name for settings.
	 *
	 * @var string
	 */
	private $option_name = 'heyjarvis_settings';

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_action( 'admin_menu', array( $this, 'add_admin_menu' ) );
		add_action( 'admin_init', array( $this, 'register_settings' ) );
		add_action( 'admin_enqueue_scripts', array( $this, 'enqueue_admin_assets' ) );
	}

	/**
	 * Add admin menu under Settings.
	 */
	public function add_admin_menu() {
		add_options_page(
			__( 'HeyJarvis Settings', 'heyjarvis-chat' ),
			__( 'HeyJarvis', 'heyjarvis-chat' ),
			'manage_options',
			'heyjarvis-chat',
			array( $this, 'render_settings_page' )
		);
	}

	/**
	 * Register settings fields.
	 */
	public function register_settings() {
		register_setting(
			'heyjarvis_chat_settings',
			$this->option_name,
			array(
				'type'              => 'array',
				'sanitize_callback' => array( $this, 'sanitize_settings' ),
				'default'           => array(),
			)
		);

		// Practice ID.
		add_settings_section(
			'heyjarvis_chat_general',
			__( 'General Settings', 'heyjarvis-chat' ),
			array( $this, 'render_general_section' ),
			'heyjarvis_chat'
		);

		add_settings_field(
			'practice_id',
			__( 'Practice ID', 'heyjarvis-chat' ),
			array( $this, 'render_text_field' ),
			'heyjarvis_chat',
			'heyjarvis_chat_general',
			array(
				'label_for'   => 'practice_id',
				'description' => __( 'Your HeyJarvis practice identifier.', 'heyjarvis-chat' ),
				'required'    => true,
			)
		);

		add_settings_field(
			'api_url',
			__( 'API URL', 'heyjarvis-chat' ),
			array( $this, 'render_text_field' ),
			'heyjarvis_chat',
			'heyjarvis_chat_general',
			array(
				'label_for'   => 'api_url',
				'description' => __( 'HeyJarvis API endpoint URL.', 'heyjarvis-chat' ),
				'default'     => 'https://api.heyjarvis.com/api',
			)
		);

		// Appearance section.
		add_settings_section(
			'heyjarvis_chat_appearance',
			__( 'Appearance', 'heyjarvis-chat' ),
			array( $this, 'render_appearance_section' ),
			'heyjarvis_chat'
		);

		add_settings_field(
			'primary_color',
			__( 'Primary Color', 'heyjarvis-chat' ),
			array( $this, 'render_color_field' ),
			'heyjarvis_chat',
			'heyjarvis_chat_appearance',
			array(
				'label_for'   => 'primary_color',
				'description' => __( 'Primary color for the chat widget.', 'heyjarvis-chat' ),
				'default'     => '#2563EB',
			)
		);

		add_settings_field(
			'widget_title',
			__( 'Widget Title', 'heyjarvis-chat' ),
			array( $this, 'render_text_field' ),
			'heyjarvis_chat',
			'heyjarvis_chat_appearance',
			array(
				'label_for'   => 'widget_title',
				'description' => __( 'Title displayed in the chat widget header.', 'heyjarvis-chat' ),
				'default'     => 'HeyJarvis Chat',
			)
		);

		add_settings_field(
			'subtitle',
			__( 'Subtitle', 'heyjarvis-chat' ),
			array( $this, 'render_text_field' ),
			'heyjarvis_chat',
			'heyjarvis_chat_appearance',
			array(
				'label_for'   => 'subtitle',
				'description' => __( 'Subtitle displayed below the widget title.', 'heyjarvis-chat' ),
				'default'     => 'AI Dental Concierge',
			)
		);

		add_settings_field(
			'welcome_message',
			__( 'Welcome Message', 'heyjarvis-chat' ),
			array( $this, 'render_textarea_field' ),
			'heyjarvis_chat',
			'heyjarvis_chat_appearance',
			array(
				'label_for'   => 'welcome_message',
				'description' => __( 'Initial message shown when the chat opens.', 'heyjarvis-chat' ),
				'default'     => 'Hello! How can I help you with your dental appointment today?',
			)
		);
	}

	/**
	 * Sanitize settings before saving.
	 *
	 * @param array $input Raw input.
	 * @return array Sanitized settings.
	 */
	public function sanitize_settings( $input ) {
		$sanitized = array();

		if ( ! is_array( $input ) ) {
			return $sanitized;
		}

		$sanitized['practice_id']     = isset( $input['practice_id'] ) ? sanitize_text_field( $input['practice_id'] ) : '';
		$sanitized['api_url']         = isset( $input['api_url'] ) ? esc_url_raw( $input['api_url'] ) : 'https://api.heyjarvis.com/api';
		$sanitized['primary_color']   = isset( $input['primary_color'] ) ? sanitize_hex_color( $input['primary_color'] ) : '#2563EB';
		$sanitized['widget_title']    = isset( $input['widget_title'] ) ? sanitize_text_field( $input['widget_title'] ) : 'HeyJarvis Chat';
		$sanitized['welcome_message'] = isset( $input['welcome_message'] ) ? wp_kses_post( $input['welcome_message'] ) : '';
		$sanitized['subtitle']        = isset( $input['subtitle'] ) ? sanitize_text_field( $input['subtitle'] ) : 'AI Dental Concierge';

		return $sanitized;
	}

	/**
	 * Render general section description.
	 */
	public function render_general_section() {
		echo '<p>' . esc_html__( 'Configure your HeyJarvis AI Dental Concierge integration.', 'heyjarvis-chat' ) . '</p>';
	}

	/**
	 * Render appearance section description.
	 */
	public function render_appearance_section() {
		echo '<p>' . esc_html__( 'Customize the look and feel of your chat widget.', 'heyjarvis-chat' ) . '</p>';
	}

	/**
	 * Render a text input field.
	 *
	 * @param array $args Field arguments.
	 */
	public function render_text_field( $args ) {
		$settings  = get_option( $this->option_name, array() );
		$field_key = $args['label_for'];
		$value     = isset( $settings[ $field_key ] ) ? $settings[ $field_key ] : ( $args['default'] ?? '' );
		?>
		<input type="text"
			id="<?php echo esc_attr( $field_key ); ?>"
			name="<?php echo esc_attr( $this->option_name . '[' . $field_key . ']' ); ?>"
			value="<?php echo esc_attr( $value ); ?>"
			class="regular-text"
			<?php echo isset( $args['required'] ) && $args['required'] ? 'required' : ''; ?>
		/>
		<?php if ( ! empty( $args['description'] ) ) : ?>
			<p class="description"><?php echo esc_html( $args['description'] ); ?></p>
		<?php endif; ?>
		<?php
	}

	/**
	 * Render a color picker field.
	 *
	 * @param array $args Field arguments.
	 */
	public function render_color_field( $args ) {
		$settings  = get_option( $this->option_name, array() );
		$field_key = $args['label_for'];
		$value     = isset( $settings[ $field_key ] ) ? $settings[ $field_key ] : ( $args['default'] ?? '#2563EB' );
		?>
		<input type="color"
			id="<?php echo esc_attr( $field_key ); ?>"
			name="<?php echo esc_attr( $this->option_name . '[' . $field_key . ']' ); ?>"
			value="<?php echo esc_attr( $value ); ?>"
		/>
		<?php if ( ! empty( $args['description'] ) ) : ?>
			<p class="description"><?php echo esc_html( $args['description'] ); ?></p>
		<?php endif; ?>
		<?php
	}

	/**
	 * Render a textarea field.
	 *
	 * @param array $args Field arguments.
	 */
	public function render_textarea_field( $args ) {
		$settings  = get_option( $this->option_name, array() );
		$field_key = $args['label_for'];
		$value     = isset( $settings[ $field_key ] ) ? $settings[ $field_key ] : ( $args['default'] ?? '' );
		?>
		<textarea id="<?php echo esc_attr( $field_key ); ?>"
			name="<?php echo esc_attr( $this->option_name . '[' . $field_key . ']' ); ?>"
			rows="4"
			class="large-text"><?php echo esc_textarea( $value ); ?></textarea>
		<?php if ( ! empty( $args['description'] ) ) : ?>
			<p class="description"><?php echo esc_html( $args['description'] ); ?></p>
		<?php endif; ?>
		<?php
	}

	/**
	 * Render the settings page.
	 */
	public function render_settings_page() {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}
		?>
		<div class="wrap">
			<h1><?php echo esc_html( get_admin_page_title() ); ?></h1>
			<?php settings_errors( 'heyjarvis_chat_messages' ); ?>
			<form action="options.php" method="post">
				<?php
				settings_fields( 'heyjarvis_chat_settings' );
				do_settings_sections( 'heyjarvis_chat' );
				submit_button( __( 'Save Settings', 'heyjarvis-chat' ) );
				?>
			</form>
		</div>
		<?php
	}

	/**
	 * Enqueue admin assets.
	 *
	 * @param string $hook Current admin page hook.
	 */
	public function enqueue_admin_assets( $hook ) {
		// Only load on HeyJarvis settings page.
		if ( 'settings_page_heyjarvis-chat' !== $hook ) {
			return;
		}

		wp_enqueue_style(
			'heyjarvis-chat-admin-css',
			HEYJARVIS_CHAT_PLUGIN_URL . 'admin/css/admin.css',
			array(),
			HEYJARVIS_CHAT_VERSION
		);

		wp_enqueue_script(
			'heyjarvis-chat-admin-js',
			HEYJARVIS_CHAT_PLUGIN_URL . 'admin/js/admin.js',
			array( 'jquery', 'wp-color-picker' ),
			HEYJARVIS_CHAT_VERSION,
			true
		);

		// Enqueue WordPress color picker dependencies.
		wp_enqueue_style( 'wp-color-picker' );
	}
}
