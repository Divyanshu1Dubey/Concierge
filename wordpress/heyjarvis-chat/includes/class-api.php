<?php
/**
 * HeyJarvis Chat API Communication
 *
 * @package HeyJarvis_Chat
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * HeyJarvis_API class.
 */
class HeyJarvis_API {

	/**
	 * Plugin settings.
	 *
	 * @var array
	 */
	private $settings;

	/**
	 * Constructor.
	 */
	public function __construct() {
		$this->settings = get_option( 'heyjarvis_settings', array() );
	}

	/**
	 * Get the API base URL.
	 *
	 * @return string
	 */
	private function get_api_url() {
		return ! empty( $this->settings['api_url'] )
			? trailingslashit( $this->settings['api_url'] )
			: 'https://api.heyjarvis.com/api/';
	}

	/**
	 * Make a POST request to the HeyJarvis API.
	 *
	 * @param string $endpoint API endpoint.
	 * @param array  $data     Request body data.
	 * @return array|WP_Error Response data or WP_Error on failure.
	 */
	private function post( $endpoint, $data = array() ) {
		$url = $this->get_api_url() . ltrim( $endpoint, '/' );

		$args = array(
			'method'      => 'POST',
			'timeout'     => 30,
			'headers'     => array(
				'Content-Type'  => 'application/json',
				'Accept'        => 'application/json',
			),
			'body'        => wp_json_encode( $data ),
			'data_format' => 'body',
		);

		$response = wp_remote_post( $url, $args );

		if ( is_wp_error( $response ) ) {
			return $response;
		}

		$code = wp_remote_retrieve_response_code( $response );
		$body = wp_remote_retrieve_body( $response );

		if ( $code >= 400 ) {
			return new WP_Error(
				'heyjarvis_api_error',
				sprintf(
					/* translators: %d: HTTP status code */
					__( 'HeyJarvis API error: HTTP %d', 'heyjarvis-chat' ),
					$code
				)
			);
		}

		$decoded = json_decode( $body, true );

		if ( json_last_error() !== JSON_ERROR_NONE ) {
			return new WP_Error(
				'heyjarvis_json_error',
				__( 'HeyJarvis API returned invalid JSON.', 'heyjarvis-chat' )
			);
		}

		return $decoded;
	}

	/**
	 * Make a GET request to the HeyJarvis API.
	 *
	 * @param string $endpoint API endpoint.
	 * @param array  $query    Query parameters.
	 * @return array|WP_Error Response data or WP_Error on failure.
	 */
	private function get( $endpoint, $query = array() ) {
		$url = $this->get_api_url() . ltrim( $endpoint, '/' );

		if ( ! empty( $query ) ) {
			$url = add_query_arg( $query, $url );
		}

		$args = array(
			'method'      => 'GET',
			'timeout'     => 30,
			'headers'     => array(
				'Accept' => 'application/json',
			),
		);

		$response = wp_remote_get( $url, $args );

		if ( is_wp_error( $response ) ) {
			return $response;
		}

		$code = wp_remote_retrieve_response_code( $response );
		$body = wp_remote_retrieve_body( $response );

		if ( $code >= 400 ) {
			return new WP_Error(
				'heyjarvis_api_error',
				sprintf(
					/* translators: %d: HTTP status code */
					__( 'HeyJarvis API error: HTTP %d', 'heyjarvis-chat' ),
					$code
				)
			);
		}

		$decoded = json_decode( $body, true );

		if ( json_last_error() !== JSON_ERROR_NONE ) {
			return new WP_Error(
				'heyjarvis_json_error',
				__( 'HeyJarvis API returned invalid JSON.', 'heyjarvis-chat' )
			);
		}

		return $decoded;
	}

	/**
	 * Verify a practice ID is valid.
	 *
	 * @param string $practice_id Practice identifier.
	 * @return bool|WP_Error True if valid, WP_Error on failure.
	 */
	public function verify_practice( $practice_id ) {
		$result = $this->post( 'practices/verify', array( 'practice_id' => $practice_id ) );

		if ( is_wp_error( $result ) ) {
			return $result;
		}

		return ! empty( $result['valid'] );
	}

	/**
	 * Create a new conversation for a practice.
	 *
	 * @param string $practice_id Practice identifier.
	 * @return array|WP_Error Conversation data or WP_Error on failure.
	 */
	public function create_conversation( $practice_id ) {
		$result = $this->post(
			'conversations',
			array(
				'practice_id' => sanitize_text_field( $practice_id ),
			)
		);

		if ( is_wp_error( $result ) ) {
			return $result;
		}

		return $result;
	}

	/**
	 * Send a message in an existing conversation.
	 *
	 * @param string $conversation_id Conversation identifier.
	 * @param string $message         User message content.
	 * @return array|WP_Error Response data or WP_Error on failure.
	 */
	public function send_message( $conversation_id, $message ) {
		$result = $this->post(
			'conversations/' . rawurlencode( $conversation_id ) . '/messages',
			array(
				'content' => sanitize_text_field( $message ),
			)
		);

		if ( is_wp_error( $result ) ) {
			return $result;
		}

		return $result;
	}

	/**
	 * Retrieve messages for a conversation.
	 *
	 * @param string $conversation_id Conversation identifier.
	 * @return array|WP_Error Messages array or WP_Error on failure.
	 */
	public function get_messages( $conversation_id ) {
		$result = $this->get(
			'conversations/' . rawurlencode( $conversation_id ) . '/messages',
			array( 'limit' => 50 )
		);

		if ( is_wp_error( $result ) ) {
			return $result;
		}

		return $result;
	}

	/**
	 * Check whether the API is reachable.
	 *
	 * @return bool True if API responds with 200.
	 */
	public function health_check() {
		$url    = $this->get_api_url() . 'health';
		$response = wp_remote_get( $url, array( 'timeout' => 5 ) );

		return ! is_wp_error( $response )
			&& wp_remote_retrieve_response_code( $response ) === 200;
	}
}
