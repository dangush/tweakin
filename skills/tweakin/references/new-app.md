# Research a native app tweak

Begin with a concrete behavior and a readable, locally acquired binary. Record the app's bundle identifier, version, architecture, device OS, and a private SHA-256 hash of the input. Identify the screens and entry points where the behavior appears, together with interactions that must remain usable.

## Look for prior work

Search GitHub for the app, its internal class names, and existing tweaks. Read the actual source and license before adapting it. A class name found in a tweak is a hypothesis about your version. Confirm it against the acquired binary and the running app. Record source revisions and distinguish copied hook locations from independently discovered behavior.

The Instagram example builds on [SCInsta](https://github.com/SoCuul/SCInsta). [fishhook](https://github.com/facebook/fishhook) provides C-symbol rebinding. These tools solve different problems from [UnfairPlay's decryption](https://github.com/DrWhax/unfairplay) and [ipatool's acquisition](https://github.com/majd/ipatool).

## Inspect metadata and execution

For a supported thin arm64 IPA, the included command reports basic architecture and encryption information:

```sh
python3 "$skill_dir/scripts/instagram.py" inspect --ipa "$work/App.decrypted.ipa"
```

The inspection command's name clues are Instagram-specific. For another app, use a general Objective-C metadata reader, such as [go-macho](https://github.com/blacktop/go-macho), and inspect relevant methods with [Ghidra](https://github.com/NationalSecurityAgency/ghidra) or another disassembler. Objective-C class names, selectors, and type encodings can survive removal of ordinary debug symbols. Swift and C++ expose different amounts of useful information.

Search for controller, scroll-view, feed-model, and data-source relationships relevant to the feature. Inspect the corresponding implementations and callers. When static evidence is insufficient, instrument a development-signed local build or use a debugger to observe calls and objects while exercising the feature. Keep observations free of message content, credentials, and account identifiers.

`ipsw class-dump BINARY --class '^Name$' --re -V` from [ipsw](https://github.com/blacktop/ipsw) prints typed method signatures. Check embedded frameworks too; Instagram defines `IGMedia` and `IGAdItem` in `FBSharedFramework`. `NSClassFromString` accepts mangled Swift names such as `_TtC21IGThreadsInFeedModels20IGThreadsInFeedModel`.

When filtering a data source, record class names in diagnostics. Instagram's diagnostics revealed that Home ads were `IGAdItem` objects, which static inspection had missed.

Do not infer a method's semantics from its name alone. Establish which screens use it, which arguments it receives, what the return value represents, and whether another path restores the original behavior.

## Choose a narrow hook

Prefer changing a specific app class over globally changing UIKit behavior. For example, a Reel player's scrolling can be independent of video playback and comments. A feed's displayed objects can be filtered without replacing its media decoder or network protocol.

Check the actual ABI and method type encoding before casting a function pointer. Handle inherited methods without accidentally changing their superclass for unrelated screens. Preserve the original implementation for work the tweak still needs. Account for lifecycle methods, automatic advancement, refresh, and repeated data-source calls.

The Instagram source demonstrates these patterns, but its storage adjustments, keychain group, tab configuration, and model filters belong to that recipe. Its runtime guard checks the return type and argument count, not every argument type. A new recipe needs its own ABI review and acceptance.

If a feature lives entirely in native Swift, C++, generated UI, or server-side logic, a small Objective-C hook may not be sufficient. Report what the binary and runtime establish before committing to an implementation.

## Package a separate recipe

Keep app-specific source, version constraints, source attribution, build instructions, and acceptance together. Start from the Instagram packager only where its assumptions hold. Do not silently reuse its identifier, profile, entitlement, extension-removal, or storage policy for another app.

Choose a stable separate bundle identifier. Work on a staged copy, keep the original unchanged, sign nested code before the main app, and verify the signatures before installation. Reject encrypted images or unsupported binary layouts. Use explicit local inputs for every signing dependency.

## Record acceptance

For each supported version, record what was inspected statically, what compiled, what passed signature verification, what launched, and which behaviors were tested on a phone. Include alternate entry points, adjacent interactions, refreshes, and account changes where applicable. Test an in-place signing refresh before promising recipients that their login survives weekly renewal.

Document missing capabilities, unsupported versions, and untested behavior. A modified app may be detected by its identity, loaded libraries, runtime changes, or server attestation. Keep integrity work separate from the requested feature change and do not claim invisibility.
