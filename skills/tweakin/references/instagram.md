# Build Instagram Focus

Use this recipe with a decrypted Instagram 418.2.0 IPA. The main executable and retained frameworks must be thin arm64 images. Other architectures, universal binaries, and other Instagram versions are rejected. The tweak targets iOS 16.3 or newer and was accepted on iOS 18.6.2.

## Prepare your inputs

Use a Mac with full Xcode, its iPhone SDK, and Python 3.10 or newer. Select Xcode in **Xcode > Settings > Locations > Command Line Tools**. Keep your files in a private directory outside the checkout.

```sh
work="$HOME/tweakin-work"
mkdir -p "$work"
chmod 700 "$work"
skill_dir="$HOME/.codex/skills/tweakin"
python3 "$skill_dir/scripts/instagram.py" inspect --ipa "$work/Instagram.decrypted.ipa"
```

Supply the IPA using [the acquisition guide](acquisition.md). Inspection reports bundle identity, version, supported image architectures, encryption flags, and known name clues. It does not validate the meaning of those names or prove that the hooks will work.

## Obtain your signing profile

1. Add your Apple account in **Xcode > Settings > Accounts**. A paid account is optional for personal development signing.
2. Connect and unlock your iPhone. Trust the Mac and enable **Settings > Privacy & Security > Developer Mode** when required.
3. Create an empty iOS app project named `FocusSigning`. Choose your own stable bundle identifier, such as `org.example.InstagramFocus`, with a namespace you control. Set **Signing & Capabilities > Team** to your account and enable automatic signing.
4. Select the connected phone as the run destination and use **Product > Build**. This registers the phone and creates a profile. Do not run the empty app over an existing Instagram Focus installation.
5. Locate the built `FocusSigning.app` through **Product > Show Build Folder in Finder**, under `Products/Debug-iphoneos`. Show its package contents and copy `embedded.mobileprovision` to your private working directory as `profile.mobileprovision`.

An alternative after Xcode has registered the phone is to build the project with a predictable output directory:

```sh
xcodebuild -project "$work/FocusSigning/FocusSigning.xcodeproj" \
  -scheme FocusSigning -configuration Debug \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$work/signing" -allowProvisioningUpdates build
cp "$work/signing/Build/Products/Debug-iphoneos/FocusSigning.app/embedded.mobileprovision" "$work/profile.mobileprovision"
security find-identity -v -p codesigning
```

Use the 40-character SHA-1 fingerprint of the development certificate that belongs to the profile. Its private key remains in your Mac's keychain. The build tool checks that the profile authorizes that certificate, the bundle identifier, and the keychain group. It also rejects expired profiles.

## Build the modified app

Replace the example bundle identifier and certificate fingerprint with your own values. The identifier must match the signing profile and differ from stock Instagram's identifier.

```sh
python3 "$skill_dir/scripts/instagram.py" build \
  --ipa "$work/Instagram.decrypted.ipa" \
  --profile "$work/profile.mobileprovision" \
  --identity YOUR_40_CHARACTER_CERTIFICATE_SHA1 \
  --bundle-id org.example.InstagramFocus \
  --output "$work/InstagramFocus.ipa"
```

The command compiles the included source, stages a copy, inserts a dylib load command in verified unused header padding, configures isolated storage, and signs the result. It strips Store licensing files, old signatures, Watch components, and all app extensions. It verifies native signatures before publishing the output. Existing output files are refused, and the input IPA remains unchanged.

To compile only the tweak without an IPA or signing profile:

```sh
python3 "$skill_dir/scripts/instagram.py" compile --output "$work/InstagramFocus.dylib"
```

The library source is at `assets/instagram-focus/src/InstagramFocus.m`. A generic injection tool still needs to configure `InstagramFocusKeychainGroup` from the final profile and sign the complete app. Sideloadly and AltStore integration have not been accepted with this package.

## Install and test

Keep the phone unlocked. Extract the new IPA into a fresh local directory and select your own phone from the device list:

```sh
ditto -x -k "$work/InstagramFocus.ipa" "$work/install"
xcrun devicectl list devices
xcrun devicectl device install app --device YOUR_DEVICE_IDENTIFIER "$work/install/Payload/InstagramFocus.app"
```

If iOS reports **Untrusted Developer**, trust your developer account under **Settings > General > VPN & Device Management**. Launch Instagram Focus and log in on the phone.

Check each behavior:

1. Open a specific Reel from a DM, search, and a profile. Confirm playback and controls work, manual swipes do not advance, and playback does not automatically advance.
2. Search for an account and content. Confirm results and navigation work while the Explore recommendation grid stays hidden.
3. Confirm the Reels tab is absent. Switch among the remaining tabs and check that the selected icon matches the visible screen.
4. Check Home with followed, unfollowed, and your own posts. Confirm suggestions, ads, and promotions are filtered and Home stops at the caught-up marker or the post limit. Refresh and repeat.
5. Watch several Stories in a row. Confirm no ads appear and navigation still works.
6. Check comments, ordinary post carousels, DMs, profiles, and account switching.

Compilation, signing, and hook availability are separate from these phone checks. The tweak writes content-free hook status and counters to `Library/Caches/InstagramFocus/status.json` in its app container. These counters do not establish every edge case.

Leave the app open on the tested screen for a few seconds, then copy the file:

```sh
xcrun devicectl device copy from --device YOUR_DEVICE_IDENTIFIER \
  --domain-type appDataContainer --domain-identifier YOUR_BUNDLE_ID \
  --source Library/Caches/InstagramFocus/status.json \
  --destination "$work/status.json"
```

`homeObjectClasses` lists the model classes in the latest Home result, which identifies unit types the filters miss. A `No provider was found` message from `devicectl` did not prevent installation in testing.

## Refresh the signature

Free Personal Team profiles expire after seven days; paid team development profiles last about a year, and a team wildcard profile (`TEAMID.*`) also works with the build tool. Refresh the profile through Xcode, build to a new output filename, and install over the existing app using the same bundle identifier and signing team. An in-place update normally preserves the app's data. Do not uninstall it as part of a routine refresh. Keep your original decrypted input privately for rebuilding.

See [Apple's developer account overview](https://developer.apple.com/help/account/basics/about-your-developer-account) for current signing limits. Paid membership alone does not restore the removed app extensions or push capability.

## Behavior and limits

The patch leaves individual Reel playback in place and disables the collection view's scrolling and separate auto-scroll configuration. It removes the Reels navigation surface from both tab layout and swipe navigation. It hides Explore recommendations while retaining search.

Home operates on Instagram's display models. It removes known suggestion models and suggested media, checks the author's native followed-by-current-user flag when available, and allows your own posts. Items with unavailable relationship status can remain. Home ends at the native caught-up marker or after 30 distinct posts per data-source lifetime. Refreshes or account changes may create a new lifetime. This is a display limit; it does not guarantee that all background fetching stops.

Home also removes ads and the Threads and Meta AI Vibes promotion units. In 418.2.0, Home ads are standalone `IGAdItem` objects, not flagged `IGMedia`. Paid-partnership posts remain.

Stories drop sponsored reels in `IGStoryViewerDataStore` before they reach the viewer.

Filtering can leave Home very short, and Instagram may not load another page; in one session, 1 of 19 media items was from a followed account. Pull to refresh for a new page.

The minimal signing profile omits push-notification capability, and the recipe removes app extensions and Watch components. Posting, calls, background behavior, and long-term operation have not been separately accepted. The modifications remain detectable through changed identity, loaded code, or integrity checks.

## Verification record

The original native patch was user-accepted on Instagram 418.2.0 and iOS 18.6.2. The phone user confirmed individual Reels, preserved search, filtered and bounded Home, and the removed Reels navigation button. That acceptance applies to the original integration.

The portable CLI has synthetic tests for binary injection, archive handling, profile authorization, and app preparation. A standalone copy of the skill compiled its included native source with the iPhone SDK without the original workspace. Preparation was also exercised against a locally acquired compatible IPA, and the staged app passed native deep, strict signature verification with a local ad-hoc signature. That check does not establish device provisioning. The portable build workflow still requires fresh acceptance on a recipient's phone, including login and an in-place signing refresh. Do not treat the original phone check as acceptance of a new signing setup.

The portable CLI was later accepted end to end on iOS 27.0.1, using the acquisition guide and a paid team's wildcard profile. All hooks installed, and the user confirmed the original behaviors.

The ad and promotion filters (patch version 3) were phone-tested in a local variant with minor preference differences. No ads appeared in Home or Stories, and the counters recorded 8 Home ads and 6 Story ad reels removed. Neither the Threads nor the Vibes unit appeared, so those filters are verified only statically. This exact source compiled and passed signature verification; phone acceptance is pending.
