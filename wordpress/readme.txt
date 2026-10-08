=== HeyJarvis Chat Widget ===
Contributors: heyjarvis
Tags: chat, ai, chatbot, widget, dental
Requires at least: 5.0
Tested up to: 6.4
Stable tag: 1.0.0
License: MIT
License URI: https://opensource.org/licenses/MIT

Embeddable AI chat widget for your WordPress website. Provides intelligent conversational AI to help visitors with FAQs, appointments, and practice information.

== Description ==

HeyJarvis Chat Widget adds an embeddable AI-powered chat widget to your WordPress website. Help your visitors get instant answers to common questions, schedule appointments, and learn about your services through an intelligent conversational interface.

= Features =

* Floating chat button with pulse animation
* Slide-up chat panel with modern design
* AI-powered responses for FAQs and appointment scheduling
* Fully customizable colors, titles, and messages
* Mobile responsive (full screen on mobile devices)
* Auto-session management
* Typing indicators
* Error handling with graceful fallbacks
* Shortcode support: [heyjarvis]
* Settings page in WordPress admin

= Configuration =

1. Go to **Settings > HeyJarvis** in your WordPress admin
2. Enter your **Practice Slug** (unique identifier for your practice)
3. Enter your **API URL** (your HeyJarvis API endpoint)
4. Customize the **Button Color**, **Title**, and **Subtitle**
5. Save settings

= Shortcode =

Use the `[heyjarvis]` shortcode in any post, page, or widget area. You can also override settings per instance:

`[heyjarvis practice_slug="my-practice" title="Custom Title"]`

== Installation ==

1. Upload the `heyjarvis` folder to the `/wp-content/plugins/` directory
2. Activate the plugin through the 'Plugins' screen in WordPress
3. Go to **Settings > HeyJarvis** to configure the widget
4. The widget will appear automatically on your site when configured

== Frequently Asked Questions ==

= How do I get a Practice Slug? =

Your Practice Slug is provided when you sign up for HeyJarvis. It's a unique identifier for your dental practice (e.g., `bright-smile-dental`).

= Where do I get the API URL? =

The API URL is provided by your HeyJarvis account. It typically looks like `https://api.heyjarvis.com` or your custom domain.

= Can I customize the widget appearance? =

Yes! Go to Settings > HeyJarvis in your WordPress admin. You can change the button color, title, and subtitle to match your brand.

= Does the widget work on mobile devices? =

Yes, the widget is fully responsive. On mobile devices, it opens in a full-screen mode for the best user experience.

= Is there a shortcode I can use? =

Yes, use `[heyjarvis]` in any post, page, or widget. You can also pass attributes to override settings: `[heyjarvis title="Custom Title"]`

== Screenshots ==

1. Chat widget button (bottom-right corner)
2. Chat panel with conversation
3. Settings page in WordPress admin

== Changelog ==

= 1.0.0 =
* Initial release
* Floating chat button with animations
* Slide-up chat panel
* AI-powered conversations
* Shortcode support
* Admin settings page
* Mobile responsive design

== Upgrade Notice ==

= 1.0.0 =
Initial release of HeyJarvis Chat Widget.
