# 0041. Portfolio code license

- Status: accepted
- Date: 2026-10-05

The owner approved GPL-3.0-or-later for original Chess Analytics Lab code.
This aligns with the direct python-chess dependency (`chess==1.11.2`), which is
GPL-3.0-or-later. Add the full GPLv3 license text, declare the SPDX expression
in package metadata, and update README and third-party notices. This decision
does not relicense dependencies or Lichess CC0 data. Use the collective project
name for attribution pending any optional personal-name preference. Historical
review and release-check reports retain their original pre-decision state.
The source archive initially admitted `.env.example` files from ignored
clean-checkout scratch directories; an explicit sdist `work/**` exclusion removed
them. The wheel and source archive both include the selected license.
