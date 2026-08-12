THE SEASONS WITHIN — CONSCIOUS COORDINATION COMPLETE BUILD

This package is designed to replace the app code/templates while preserving your existing database file.
DO NOT replace community_v8.db when uploading this update.

CORE EXPERIENCE
- The natal chart is the center of The Seasons Within.
- Conscious Coordination branches into love, friendship, wellness, business, collaboration and retreats.
- Home shows the member's natal placements, current Moon sign/phase, current planetary signs, season reflection, real businesses and real connection profiles.
- Uses “natal chart” terminology throughout the member experience.
- Daily reflection centers on the member's natal Moon and current season.
- Current sky reflections are reflective prompts, not predictions or financial advice.

CONSCIOUS CONNECTIONS
- No mock dater profiles are seeded for new databases; existing demo accounts are filtered from directories.
- Free connection profile includes one main photo, profile questions, natal placements, house signs and free compatibility percentages.
- Connection intentions can include love, friendship, wellness buddy, workout partner, travel partner, business, creative collaboration and retreat partner.
- Free members can browse real profiles and see compatibility percentages.
- Mutual Like/Connect is required before private texting opens.
- Free members can text after matching and receive video messages.
- The Seasons Within Membership ($10.99/month) unlocks up to 7 photos + 2 profile videos, full natal placement interpretations, deeper compatibility explanations, persistent Likes You page, video messages and video-call request controls.
- Video-call requests are built into the app; a live video provider still must be connected before real video rooms can launch.
- New compatible profile notifications are generated when intentions overlap and compatibility meets the member's threshold.

TODAY WITHIN THE SEASONS
- Displays current Moon sign, Moon phase and major current planetary signs using Swiss Ephemeris.
- Daily personal reflection is based on natal Moon + current season.
- Moon-shift notifications are created when a member returns to the app and the Moon sign has changed.
- Planning/business prompts must remain reflective. Do not present astrology as financial or investment advice.

BUSINESS NETWORK
- Full directory requires a free account.
- No mock business cards are used by the updated templates; old demo owners are filtered from listings.
- Free business profile: name, logo, description, category, area, contact information, website, social links and affiliate/outside links.
- Business Network membership: $29.99/month.
- Paid business members can build hosted business apps with services, classes, events, shop items, memberships, booking/action links and content already supported by business_items.
- Business profiles can show basic Business Conscious Coordination when both people have natal information.
- Deeper business-partnership ideas are positioned as a Business Network benefit.

RETREATS
- Mock retreat cards are removed.
- Design Your Own Retreat remains.
- Real upcoming retreats can be added later and should be shown only when actually published.

MEMBERSHIP PRICING
- Community: Free
- The Seasons Within Membership: $10.99/month
- Business Network: $29.99/month
IMPORTANT: Updating the displayed prices does NOT change existing Stripe Price objects. Create/update the matching recurring prices in Stripe and put their Price IDs into Render environment variables before taking real payments.

PERSISTENCE / RENDER
- The build supports DATA_DIR for the SQLite database and UPLOAD_DIR for member/business media.
- For local testing, it falls back to the project folder/static uploads.
- Before real members use the live app, configure persistent storage on Render (or migrate to a managed database/object-storage setup) and set DATA_DIR / UPLOAD_DIR to persistent mounted paths.
- Without persistent storage, cloud instance replacements can still erase SQLite data or uploaded media.

UPLOAD TO GITHUB
Upload these items into the ROOT of the-seasons-within-v9 and replace matching files/folders:
- app.py
- requirements.txt
- .python-version
- templates/ (replace matching HTML files)
- static/style.css
- static/seasons-within-logo.png

Do NOT upload or replace community_v8.db from another build.

FINAL CONSOLIDATED UPDATE — AUGUST 11, 2026
- Global message updated to: Connect With Intention. Discover Your Seasons Within.
- Existing plans/prices/navigation preserved.
- Business App expanded for content creators and wellness businesses.
- Paid Business Apps now support Media Kit fields, creator/business content posts, followers, profile-view statistics, collaborations, meetups/retreat offerings, booking/application links, social links, and optional extended natal-chart business profile.
- Galaxy Eve should be created from Admin > Create Galaxy Eve or Test Profiles using “Galaxy Eve — Full Complimentary Access + Creator.” This gives the account full $10.99 member features and $29.99 Business App features without charging it. Galaxy Eve then builds her own personal profile and professional creator app through the real builders.
- Admin can create two additional test profiles or grant/revoke complimentary member, Business App, Creator, or Admin access to existing users.
- Retreat page uses The Seasons Within logo and includes Create Your Private Wellness Retreat + Explore Wellness Partners.
- Public visitors can open real Business Profiles/paid Business Apps; no mock business cards are required.
