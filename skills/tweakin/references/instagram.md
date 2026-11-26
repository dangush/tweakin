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
4. Check Home with followed, unfollowed, and your own posts. Confirm suggestions, ads, and Threads or Vibes promotion units are filtered and Home stops at the caught-up marker or the post limit. Refresh and repeat.
5. Watch several followed accounts' Stories in sequence. Confirm no sponsored reels appear between them and that forward and backward navigation still works.
6. Check comments, ordinary post carousels, DMs, profiles, and account switching.

Compilation, signing, and hook availability are separate from these phone checks. The tweak writes content-free hook status and counters to `Library/Caches/InstagramFocus/status.json` in its app container. These counters do not establish every edge case.

To read the status file, keep the app open on the screen you exercised for a few seconds, then copy it from the connected phone:

```sh
xcrun devicectl device copy from --device YOUR_DEVICE_IDENTIFIER \
  --domain-type appDataContainer --domain-identifier YOUR_BUNDLE_ID \
  --source Library/Caches/InstagramFocus/status.json \
  --destination "$work/status.json"
```

The file is rewritten about a second after each recorded event. A copy taken immediately after launch contains only installation records. `homeObjectClasses` lists the model class names in the most recent Home data-source result, which identifies a new unit type that the filters do not yet recognize. Keep the file private; it contains no content, but it does describe your session.

`devicectl` may print `Failed to load provisioning paramter list ... No provider was found` before a successful install. In the accepted runs, the install completed and the app launched normally after that message.

## Refresh the signature

Free Personal Team profiles expire after seven days. A paid team's automatically managed development profile normally lasts one year. A team wildcard profile such as `TEAMID.*` with matching keychain groups satisfies the build tool's checks when your bundle identifier falls under it and the phone is registered with the team. Use a development certificate and bundle identifier that you are authorized to use within that team. Refresh the profile through Xcode, build to a new output filename, and install over the existing app using the same bundle identifier and signing team. An in-place update normally preserves the app's data. Do not uninstall it as part of a routine refresh. Keep your original decrypted input privately for rebuilding.

See [Apple's developer account overview](https://developer.apple.com/help/account/basics/about-your-developer-account) for current signing limits. Paid membership alone does not restore the removed app extensions or push capability.

## Behavior and limits

The patch leaves individual Reel playback in place and disables the collection view's scrolling and separate auto-scroll configuration. It removes the Reels navigation surface from both tab layout and swipe navigation. It hides Explore recommendations while retaining search.

Home operates on Instagram's display models. It removes known suggestion models and suggested media, checks the author's native followed-by-current-user flag when available, and allows your own posts. Items with unavailable relationship status can remain. Home ends at the native caught-up marker or after 30 distinct posts per data-source lifetime. Refreshes or account changes may create a new lifetime. This is a display limit; it does not guarantee that all background fetching stops.

Home also removes ads and two promotion units. In 418.2.0, Home ads arrive as standalone `IGAdItem` objects rather than as `IGMedia` with a sponsored flag, so a media-only check misses them. The filter also rejects media carrying `injected`, `sponsoredPostInfo`, `isSponsored`, or `isChildOfAdItem` markers. The promotion units are the Threads section (`IGThreadsInFeedModels.IGThreadsInFeedModel`), the Threads profile upsell card, and the Meta AI Vibes unit (`IGVibesInFeedModels.IGVibesInFeedModel`). Paid-partnership posts from followed accounts are ordinary posts and remain.

Stories remove sponsored reels before they reach the viewer. `IGStoryViewerDataStore` receives the viewer's reel list through `replaceModelItems:` and `replaceModelItems:maxCount:`. The hook drops `IGStoryViewerViewModel` entries that Instagram marks as multi-author carousel or multi-ads grid ads, or whose items are all ad-marked. If every entry would be removed, the list is left unchanged to avoid an empty viewer.

The filters can leave Home short. In one accepted session, Instagram's first Home page contained 19 media items, of which 1 came from a followed account; the rest were suggestions or unfollowed authors. Home did not load another page from the short list. Pull to refresh to request a new page. Automatically requesting additional pages is not implemented.

The minimal signing profile omits push-notification capability, and the recipe removes app extensions and Watch components. Posting, calls, background behavior, and long-term operation have not been separately accepted. The modifications remain detectable through changed identity, loaded code, or integrity checks.

## Verification record

The original native patch was user-accepted on Instagram 418.2.0 and iOS 18.6.2. The phone user confirmed individual Reels, preserved search, filtered and bounded Home, and the removed Reels navigation button. That acceptance applies to the original integration.

The portable CLI has synthetic tests for binary injection, archive handling, profile authorization, and app preparation. A standalone copy of the skill compiled its included native source with the iPhone SDK without the original workspace. Preparation was also exercised against a locally acquired compatible IPA, and the staged app passed native deep, strict signature verification with a local ad-hoc signature. That check does not establish device provisioning. The portable build workflow still requires fresh acceptance on a recipient's phone, including login and an in-place signing refresh. Do not treat the original phone check as acceptance of a new signing setup.

The portable CLI was then exercised end to end on an iPhone17,1 running iOS 27.0.1. The input came from the acquisition guide's ipatool and UnfairPlay workflow, with UnfairPlay reporting verified plaintext for all 14 encrypted images. The build used a paid team's wildcard development profile. All hooks reported installation, and the phone user accepted the original behaviors: individual Reels without advancement, the removed Reels tab, preserved search with the hidden Explore grid, and filtered Home. Successive builds were installed in place over the same bundle identifier.

The ad and promotion filters (patch version 3) were added from static inspection of 418.2.0 with `ipsw class-dump` and runtime class-name diagnostics. They were phone-tested in a local variant on the same device, and the user reported no ads in Home or Stories. The status counters recorded 8 removed Home `IGAdItem` objects and 6 removed Story ad reels. The Threads and Vibes filters compiled and installed, but neither unit appeared during testing, so they are verified only statically. That variant differed from this source in personal preferences: it kept `IGInFeedStoriesTrayModel` and unknown-relationship posts, and it removed the DM Notes tray. This exact source compiled and passed signature verification; its separate phone acceptance is pending.
