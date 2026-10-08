/**
 * HeyJarvis Chat — Admin JavaScript
 *
 * @package HeyJarvis_Chat
 */

(function ($) {
	'use strict';

	/**
	 * Sync color picker with text input and vice-versa.
	 */
	$(document).ready(function () {
		$('.hj-color-text').on('input', function () {
			var val = $(this).val();
			if (/^#[0-9a-fA-F]{6}$/.test(val)) {
				$(this).siblings('.hj-color-picker').val(val);
			}
		});

		$('.hj-color-picker').on('input change', function () {
			$(this).siblings('.hj-color-text').val($(this).val());
		});
	});

	/**
	 * Verify practice ID via AJAX.
	 */
	window.heyjarvisVerifyPractice = function (practiceId) {
		var $btn   = $('#hj-verify-btn');
		var $status = $('#hj-verify-status');

		if (!practiceId) {
			$status.html(
				'<span class="hj-status hj-status--error">' +
				HeyJarvisAdmin.i18n.enterPracticeId +
				'</span>'
			);
			return;
		}

		$btn.prop('disabled', true).text(HeyJarvisAdmin.i18n.verifying);
		$status.html('<span class="hj-status hj-status--pending">' + HeyJarvisAdmin.i18n.verifying + '</span>');

		$.ajax({
			url: HeyJarvisAdmin.ajaxUrl,
			type: 'POST',
			data: {
				action: 'heyjarvis_verify_practice',
				nonce:  HeyJarvisAdmin.nonce,
				practice_id: practiceId,
			},
			success: function (response) {
				if (response.success) {
					$status.html(
						'<span class="hj-status hj-status--success">' +
						HeyJarvisAdmin.i18n.verified +
						'</span>'
					);
				} else {
					var msg = response.data || HeyJarvisAdmin.i18n.verificationFailed;
					$status.html(
						'<span class="hj-status hj-status--error">' + msg + '</span>'
					);
				}
			},
			error: function () {
				$status.html(
					'<span class="hj-status hj-status--error">' +
					HeyJarvisAdmin.i18n.connectionError +
					'</span>'
				);
			},
			complete: function () {
				$btn.prop('disabled', false).text(HeyJarvisAdmin.i18n.verify);
			},
		});
	};

})(jQuery);
