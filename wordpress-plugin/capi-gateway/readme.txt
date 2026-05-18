=== CAPI Gateway — Server-Side Tracking ===
Contributors: capigw
Tags: facebook, capi, server-side tracking, woocommerce, pixel, ga4, tiktok
Requires at least: 5.8
Tested up to: 6.7
Requires PHP: 7.4
Stable tag: 1.1.2
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Server-Side Facebook CAPI, TikTok, and GA4 tracking for WooCommerce with deferred purchase support.

== Description ==

CAPI Gateway প্লাগইন আপনার WooCommerce স্টোরের সকল ইভেন্ট (PageView, ViewContent, AddToCart, InitiateCheckout, Purchase) সার্ভার-সাইড ট্র্যাকিং দিয়ে Facebook, TikTok এবং GA4-এ পাঠায়।

**মূল ফিচারসমূহ:**

* ✅ **Zero Configuration:** শুধু API Key বসান, বাকি সব অটোমেটিক
* 🔒 **SHA-256 PII Hashing:** কাস্টমারের ইমেইল, ফোন, নাম অটোমেটিক হ্যাশ হয়ে যায়
* 📦 **Deferred Purchase (COD):** ক্যাশ-অন-ডেলিভারির জন্য অর্ডার কমপ্লিট হলে Purchase ইভেন্ট পাঠায়
* 🔄 **Auto Retry:** API কল ফেইল হলে Action Scheduler দিয়ে অটো রিট্রাই করে
* ⚡ **Cache-Safe:** AJAX দিয়ে ডাটা পাঠায় — LiteSpeed, WP Rocket ক্যাশ বাধা দেয় না
* 🛡️ **Security Plugin Compatible:** WordPress কোর ফাংশন (`wp_remote_post`) ব্যবহার করে — Wordfence ব্লক করে না

== Installation ==

1. প্লাগইনের ZIP ফাইলটি ডাউনলোড করুন
2. WordPress Admin → Plugins → Add New → Upload Plugin
3. ZIP ফাইলটি আপলোড করে "Install Now" ক্লিক করুন
4. প্লাগইন Activate করুন
5. বাম মেনু থেকে "CAPI Gateway" → আপনার API Key বসান → Save Settings

== Frequently Asked Questions ==

= API Key কোথায় পাবো? =
আপনার CAPI Gateway ড্যাশবোর্ডে লগিন করুন। ড্যাশবোর্ডের উপরে আপনার API Key দেখতে পাবেন।

= ক্যাশ প্লাগইন ব্যবহার করলে কি সমস্যা হবে? =
না। এই প্লাগইন AJAX এবং Server-Side PHP ব্যবহার করে ডাটা পাঠায়, তাই ক্যাশ প্লাগইন কোনো বাধা দিতে পারে না।

= Deferred Purchase কী? =
ক্যাশ-অন-ডেলিভারি (COD) অর্ডারের ক্ষেত্রে Purchase ইভেন্ট তখনই Facebook-এ পাঠানো হয় যখন আপনি অর্ডারটি "Completed" করেন। এতে ফেক অর্ডারের ডাটা Facebook-এ যায় না।

== Changelog ==

= 1.1.2 =
* Added durable outbox-friendly tracking improvements
* Added TikTok _ttp and ttclid capture for standard and custom events
* Added lightweight AJAX rate limiting for frontend tracking
* Improved checkout/cart content payloads
* Improved custom event selector safety
* Improved client setup instructions

= 1.1.0 =
* 🔒 Purchase event এখন blocking request — response verify করে success/failure ট্র্যাক করে
* 🔒 Phone number normalization ফিক্স — Python সার্ভারের সাথে hash matching ১০০% accurate
* 🔒 404 response আর success হিসেবে ধরা হয় না — proper error handling
* 🔒 WooCommerce webhook HMAC signature verification সাপোর্ট
* ⚡ Server-side atomic rate limiting — race condition মুক্ত
* ⚡ Production database safety — conditional create_all
* 📦 Plugin version bumped to 1.1.0

= 1.0.0 =
* Initial release
* PageView, ViewContent, AddToCart, InitiateCheckout, Purchase tracking
* Deferred Purchase with auto-confirm on order status change
* Action Scheduler retry queue with exponential backoff
* Admin settings page with connection test
* Order meta box showing tracking status
