---
name: tweakin
description: Develop native iOS app tweaks from locally acquired binaries, including a version-pinned Instagram Focus recipe, signing instructions, and phone verification. Use for changing an installed app's behavior or researching native hook locations.
---

# tweakin

Develop a narrow native tweak for the user's chosen app and behavior. Establish the exact app version, device OS, and required behavior before choosing hooks. Use existing local context rather than asking for information already available.

## Choose the route

For Instagram Focus, read [the Instagram recipe](references/instagram.md). It includes the source, version restrictions, signing steps, build tool, and phone acceptance procedure. Do not apply the pinned recipe to a different Instagram version without inspecting and testing that version.

For a new app or different behavior, read [the research guide](references/new-app.md). Identify the relevant native objects and methods before changing them. Research upstream tweaks as starting evidence and preserve their licenses and attribution.

For an encrypted or unavailable IPA, read [acquisition](references/acquisition.md). Acquisition, decryption, and development signing are separate steps. A connected iPhone does not by itself provide a decrypted IPA.

## Work locally

Resolve the bundled scripts and source relative to this skill directory. Use a separate private working directory for app copies, profiles, logs, and outputs. The scripts accept explicit paths and must not depend on the author's machine or private files.

Run Apple sign-in, administrator authentication, and phone trust prompts in the user's local session. Do not request passwords, verification codes, private keys, or enrollment models through chat. A request to modify an app does not authorize uploading its executable or publishing account data.

Use the narrowest class or method hook that controls the requested behavior. Preserve the original implementation where the unchanged work remains useful. Treat names and method signatures as clues, then verify their runtime meaning and side effects.

Keep the bundle identifier and signing team stable during refreshes. Do not uninstall a working app to refresh its signature. An app-specific keychain or app-group adjustment needs its own integration checks.

## Verify and hand over

Record compilation, signature verification, successful startup, and interactive acceptance separately. Test every requested entry point and adjacent interactions, including search, comments, and messages when relevant. A successful build or installed hook does not establish behavioral correctness.

State the tested version, known limits, signing expiry, and work the recipient must complete. New apps require a separate recipe and fresh acceptance. This skill does not make a modified client undetectable.
