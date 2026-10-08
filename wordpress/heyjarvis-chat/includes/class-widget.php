<?php
/**
 * HeyJarvis Chat Widget
 *
 * @package HeyJarvis_Chat
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * HeyJarvis_Widget class.
 */
class HeyJarvis_Widget extends WP_Widget {

	/**
	 * Constructor.
	 */
	public function __construct() {
		$widget_ops  = array(
			'classname'                   => 'widget_heyjarvis_chat',
			'description'                 => __( 'Embed the HeyJarvis AI Dental Concierge chat widget.', 'heyjarvis-chat' ),
			'customize_selective_refresh' => true,
		);
		$control_ops = array( 'width' => 400, 'height' => 350 );
		parent::__construct(
			'heyjarvis_chat',
			__( 'HeyJarvis Chat', 'heyjarvis-chat' ),
			$widget_ops,
			$control_ops
		);
	}

	/**
	 * Output the widget settings form in admin.
	 *
	 * @param array $instance Current widget instance settings.
	 */
	public function form( $instance ) {
		$defaults = array(
			'title'       => __( 'HeyJarvis Chat', 'heyjarvis-chat' ),
			'practice_id' => '',
		);
		$instance = wp_parse_args( (array) $instance, $defaults );

		?>
		<p>
			<label for="<?php echo esc_attr( $this->get_field_id( 'title' ) ); ?>">
				<?php esc_html_e( 'Title:', 'heyjarvis-chat' ); ?>
			</label>
			<input class="widefat"
			       id="<?php echo esc_attr( $this->get_field_id( 'title' ) ); ?>"
			       name="<?php echo esc_attr( $this->get_field_name( 'title' ) ); ?>"
			       type="text"
			       value="<?php echo esc_attr( $instance['title'] ); ?>" />
		</p>
		<p>
			<label for="<?php echo esc_attr( $this->get_field_id( 'practice_id' ) ); ?>">
				<?php esc_html_e( 'Practice ID:', 'heyjarvis-chat' ); ?>
			</label>
			<input class="widefat"
			       id="<?php echo esc_attr( $this->get_field_id( 'practice_id' ) ); ?>"
			       name="<?php echo esc_attr( $this->get_field_name( 'practice_id' ) ); ?>"
			       type="text"
			       value="<?php echo esc_attr( $instance['practice_id'] ); ?>"
			       placeholder="<?php echo esc_attr( 'e.g. practice-123' ); ?>" />
			<small><?php esc_html_e( 'Leave blank to use the default practice ID from settings.', 'heyjarvis-chat' ); ?></small>
		</p>
		<?php
	}

	/**
	 * Sanitize and save widget settings.
	 *
	 * @param array $new_instance New widget settings.
	 * @param array $old_instance Previous widget settings.
	 * @return array Sanitized settings.
	 */
	public function update( $new_instance, $old_instance ) {
		$instance          = array();
		$instance['title'] = sanitize_text_field( $new_instance['title'] );
		$instance['practice_id'] = sanitize_text_field( $new_instance['practice_id'] );

		return $instance;
	}

	/**
	 * Output the widget content on the frontend.
	 *
	 * @param array $args     Widget display arguments.
	 * @param array $instance Saved widget settings.
	 */
	public function widget( $args, $instance ) {
		$settings = get_option( 'heyjarvis_settings', array() );
		$practice_id = ! empty( $instance['practice_id'] )
			? $instance['practice_id']
			: ( ! empty( $settings['practice_id'] ) ? $settings['practice_id'] : '' );

		if ( empty( $practice_id ) ) {
			return;
		}

		$title = apply_filters( 'widget_title', $instance['title'] ?? __( 'HeyJarvis Chat', 'heyjarvis-chat' ) );

		echo $args['before_widget']; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
		if ( ! empty( $title ) ) {
			echo $args['before_title'] . esc_html( $title ) . $args['after_title']; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
		}

		heyjarvis_chat_render_embed(
			array(
				'practice_id'    => $practice_id,
				'title'          => $settings['widget_title'] ?? '',
				'subtitle'       => $settings['subtitle'] ?? '',
				'welcome_message' => $settings['welcome_message'] ?? '',
				'primary_color'  => $settings['primary_color'] ?? '#2563eb',
			)
		);

		echo $args['after_widget']; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
	}
}
