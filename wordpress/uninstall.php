<?php
/**
 * HeyJarvis Chat Widget - Uninstall Script
 *
 * This file is called when the user uninstalls the plugin.
 * It removes all plugin options from the database.
 *
 * @package HeyJarvis
 */

// Prevent direct access
if (!defined('WP_UNINSTALL_PLUGIN')) {
    exit;
}

// Remove plugin options
$options = array(
    'heyjarvis_practice_slug',
    'heyjarvis_api_url',
    'heyjarvis_button_color',
    'heyjarvis_title',
    'heyjarvis_subtitle',
);

foreach ($options as $option) {
    delete_option($option);
    delete_site_option($option);
}

// For multisite installations, remove options from all sites
if (is_multisite()) {
    global $wpdb;
    $blog_ids = $wpdb->get_col("SELECT blog_id FROM $wpdb->blogs WHERE site_id = $wpdb->siteid");
    foreach ($blog_ids as $blog_id) {
        switch_to_blog($blog_id);
        foreach ($options as $option) {
            delete_option($option);
        }
        restore_current_blog();
    }
}

// Optional: Drop custom database tables if any were created
// global $wpdb;
// $wpdb->query("DROP TABLE IF EXISTS {$wpdb->prefix}heyjarvis_sessions");
