// SPDX-License-Identifier: GPL-3.0-only
// Focus behavior adapted from SCInsta's documented native hooks.
#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <Security/Security.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import "third_party/fishhook/fishhook.h"

static const NSUInteger IFHomePostLimit = 30;
static NSString *IFOwnUserID;
static NSString *IFKeychainGroup;
static char IFHomeSeenKey;
static NSMutableDictionary *IFDiagnostics;

static void IFRecord(NSString *key, id value) {
    dispatch_async(dispatch_get_main_queue(), ^{
        static BOOL scheduled;
        if (!IFDiagnostics) IFDiagnostics = [NSMutableDictionary dictionary];
        IFDiagnostics[key] = value;
        if (scheduled) return;
        scheduled = YES;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            scheduled = NO;
            NSURL *directory = [[NSFileManager.defaultManager URLsForDirectory:NSCachesDirectory inDomains:NSUserDomainMask].firstObject URLByAppendingPathComponent:@"InstagramFocus" isDirectory:YES];
            [NSFileManager.defaultManager createDirectoryAtURL:directory withIntermediateDirectories:YES attributes:nil error:nil];
            NSData *data = [NSJSONSerialization dataWithJSONObject:IFDiagnostics options:NSJSONWritingPrettyPrinted error:nil];
            [data writeToURL:[directory URLByAppendingPathComponent:@"status.json"] atomically:YES];
        });
    });
}

static id IFObject(id object, NSString *name) {
    SEL selector = NSSelectorFromString(name);
    if (![object respondsToSelector:selector]) return nil;
    NSMethodSignature *signature = [object methodSignatureForSelector:selector];
    if (signature.numberOfArguments != 2 || signature.methodReturnType[0] != '@') return nil;
    return ((id (*)(id, SEL))objc_msgSend)(object, selector);
}

static BOOL IFBoolean(id object, NSString *name, BOOL *known) {
    SEL selector = NSSelectorFromString(name);
    NSMethodSignature *signature = [object respondsToSelector:selector] ? [object methodSignatureForSelector:selector] : nil;
    *known = signature.numberOfArguments == 2 && signature.methodReturnType[0] == 'B';
    return *known ? ((BOOL (*)(id, SEL))objc_msgSend)(object, selector) : NO;
}

static BOOL IFIs(id object, NSString *className) {
    Class class = NSClassFromString(className);
    return class && [object isKindOfClass:class];
}

static NSString *IFIdentifier(id object) {
    id pk = IFObject(object, @"pk");
    return [pk isKindOfClass:NSString.class] ? pk : [pk isKindOfClass:NSNumber.class] ? [pk stringValue] : nil;
}

static BOOL IFHook(NSString *className, NSString *selectorName, IMP replacement, IMP *original, char returnType, NSUInteger arguments) {
    Class class = NSClassFromString(className);
    SEL selector = NSSelectorFromString(selectorName);
    Method method = class ? class_getInstanceMethod(class, selector) : NULL;
    NSMethodSignature *signature = method ? [NSMethodSignature signatureWithObjCTypes:method_getTypeEncoding(method)] : nil;
    BOOL valid = signature && signature.methodReturnType[0] == returnType && signature.numberOfArguments == arguments;
    if (valid) {
        *original = method_getImplementation(method);
        if (!class_addMethod(class, selector, replacement, method_getTypeEncoding(method))) {
            class_replaceMethod(class, selector, replacement, method_getTypeEncoding(method));
        }
    }
    IFRecord([NSString stringWithFormat:@"hook.%@.%@", className, selectorName], @(valid));
    return valid;
}

static void (*IFOriginalReelSetScroll)(id, SEL, BOOL);
static void IFReelSetScroll(id self, SEL command, BOOL enabled) {
    IFOriginalReelSetScroll(self, command, NO);
}

static BOOL IFReelIsScrollEnabled(id self, SEL command) { return NO; }
static IMP IFOriginalReelIsScrollEnabled;

static void (*IFOriginalReelMove)(id, SEL);
static void IFReelMove(id self, SEL command) {
    IFOriginalReelMove(self, command);
    ((UIScrollView *)self).scrollEnabled = NO;
    IFRecord(@"reelPlayerObserved", @YES);
}

static void (*IFOriginalAutoScroll)(id, SEL, BOOL);
static void IFAutoScroll(id self, SEL command, BOOL enabled) {
    IFOriginalAutoScroll(self, command, NO);
    IFRecord(@"reelAutoAdvanceDisabled", @YES);
}

static void (*IFOriginalTabLoad)(id, SEL);
static void IFTabLoad(id self, SEL command) {
    IFOriginalTabLoad(self, command);
    IFOwnUserID = IFIdentifier(IFObject(IFObject(self, @"userSession"), @"user"));
    IFRecord(@"ownAccountRecognized", @(IFOwnUserID != nil));
}

static BOOL IFReelsSurface(id surface) {
    return [IFObject(surface, @"tabStringFromSurfaceIntent") isEqual:@"CLIPS"];
}

static id IFFilterNavigationSurfaces(id surfaces) {
    if (![surfaces isKindOfClass:NSArray.class]) return surfaces;
    NSMutableArray *filtered = [NSMutableArray arrayWithCapacity:[surfaces count]];
    for (id surface in surfaces) {
        if (!IFReelsSurface(surface)) [filtered addObject:surface];
    }
    IFRecord(@"navigationSurfaceCount", @(filtered.count));
    if (filtered.count < [surfaces count]) {
        IFRecord(@"reelsTabRemoved", @YES);
        return [filtered copy];
    }
    return surfaces;
}

static id (*IFOriginalSwipeInit)(id __attribute__((ns_consumed)), SEL, id, id, BOOL, id) __attribute__((ns_returns_retained));
static id IFSwipeInit(id self __attribute__((ns_consumed)), SEL command, id surfaces, id parent, BOOL haptics, id launchers) __attribute__((ns_returns_retained));
static id IFSwipeInit(id self __attribute__((ns_consumed)), SEL command, id surfaces, id parent, BOOL haptics, id launchers) {
    return IFOriginalSwipeInit(self, command, IFFilterNavigationSurfaces(surfaces), parent, haptics, launchers);
}

static void (*IFOriginalTabLayout)(id, SEL);
static void IFTabLayout(id self, SEL command) {
    Ivar ivar = class_getInstanceVariable(object_getClass(self), "_tabBarSurfaces");
    if (ivar && ivar_getTypeEncoding(ivar)[0] == '@') {
        id surfaces = object_getIvar(self, ivar);
        id filtered = IFFilterNavigationSurfaces(surfaces);
        if (filtered != surfaces) object_setIvarWithStrongDefault(self, ivar, filtered);
    }
    IFOriginalTabLayout(self, command);
}

static id (*IFOriginalTabButton)(id, SEL, id);
static id IFTabButton(id self, SEL command, id surface) {
    id button = IFOriginalTabButton(self, command, surface);
    return IFReelsSurface(surface) ? nil : button;
}

static NSArray *(*IFOriginalHomeObjects)(id, SEL, id);
static NSArray *IFHomeObjects(id self, SEL command, id adapter) {
    NSArray *original = IFOriginalHomeObjects(self, command, adapter);
    if (![original isKindOfClass:NSArray.class]) return original;
    NSMutableSet *seen = objc_getAssociatedObject(self, &IFHomeSeenKey);
    if (!seen) {
        seen = [NSMutableSet set];
        objc_setAssociatedObject(self, &IFHomeSeenKey, seen, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    NSMutableArray *result = [NSMutableArray arrayWithCapacity:original.count];
    NSUInteger suggestions = 0, notFollowed = 0, visiblePosts = 0;
    BOOL caughtUp = NO, limitReached = NO;
    for (id object in original) {
        if (IFIs(object, @"IGEndOfFeedDemarcatorModel")) {
            [result addObject:object];
            caughtUp = YES;
            break;
        }
        if (IFIs(object, @"IGFeedScrollableClipsModel") || IFIs(object, @"IGHScrollAYMFModel") || IFIs(object, @"IGInFeedStoriesTrayModel")) {
            suggestions++;
            continue;
        }
        if (IFIs(object, @"IGMedia")) {
            id suggested = IFObject(object, @"explorePostInFeed");
            if ([suggested respondsToSelector:@selector(boolValue)] && [suggested boolValue]) {
                suggestions++;
                continue;
            }
            id author = IFObject(object, @"user");
            BOOL relationshipKnown;
            BOOL followed = IFBoolean(author, @"followedByCurrentUser", &relationshipKnown);
            BOOL ownPost = IFOwnUserID && [IFIdentifier(author) isEqualToString:IFOwnUserID];
            if (relationshipKnown && !followed && !ownPost) {
                notFollowed++;
                continue;
            }
            id identifier = IFIdentifier(object) ?: [NSValue valueWithNonretainedObject:object];
            if (![seen containsObject:identifier]) {
                if (seen.count >= IFHomePostLimit) { limitReached = YES; break; }
                [seen addObject:identifier];
            }
            visiblePosts++;
        }
        [result addObject:object];
    }
    limitReached = limitReached || seen.count >= IFHomePostLimit;
    if (limitReached || caughtUp) {
        NSIndexSet *spinners = [result indexesOfObjectsPassingTest:^BOOL(id object, NSUInteger index, BOOL *stop) {
            return IFIs(object, @"IGSpinnerLabelViewModel");
        }];
        [result removeObjectsAtIndexes:spinners];
    }
    IFRecord(@"homeVisiblePosts", @(visiblePosts));
    IFRecord(@"homeRemovedSuggestions", @(suggestions));
    IFRecord(@"homeRemovedUnfollowedAuthors", @(notFollowed));
    IFRecord(@"homeCaughtUp", @(caughtUp));
    IFRecord(@"homeLimitReached", @(limitReached));
    IFRecord(@"homeSessionPostLimit", @(IFHomePostLimit));
    return result;
}

static void (*IFOriginalExploreGridLoad)(id, SEL);
static void IFExploreGridLoad(id self, SEL command) {
    IFOriginalExploreGridLoad(self, command);
    ((UIViewController *)self).view.hidden = YES;
    IFRecord(@"exploreRecommendationsHidden", @YES);
}

static void (*IFOriginalExploreLoad)(id, SEL);
static void IFExploreLoad(id self, SEL command) {
    IFOriginalExploreLoad(self, command);
    Ivar ivar = class_getInstanceVariable(object_getClass(self), "_shimmeringGridView");
    if (ivar && ivar_getTypeEncoding(ivar)[0] == '@') {
        id view = object_getIvar(self, ivar);
        if ([view isKindOfClass:UIView.class]) [view setHidden:YES];
    }
}

static NSURL *(*IFOriginalGroupContainer)(id, SEL, NSString *);
static NSURL *IFGroupContainer(id self, SEL command, NSString *group) {
    NSURL *original = IFOriginalGroupContainer(self, command, group);
    if (original || ![group hasPrefix:@"group."]) return original;
    NSCharacterSet *characters = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"];
    NSString *component = [group stringByAddingPercentEncodingWithAllowedCharacters:characters];
    NSURL *directory = [[NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory inDomains:NSUserDomainMask].firstObject URLByAppendingPathComponent:@"InstagramFocusGroups" isDirectory:YES];
    directory = [directory URLByAppendingPathComponent:component isDirectory:YES];
    NSError *error;
    if (![NSFileManager.defaultManager createDirectoryAtURL:directory withIntermediateDirectories:YES attributes:nil error:&error]) return nil;
    return directory;
}

static id (*IFOriginalDefaultsSuite)(id __attribute__((ns_consumed)), SEL, NSString *) __attribute__((ns_returns_retained));
static id IFDefaultsSuite(id self __attribute__((ns_consumed)), SEL command, NSString *suite) __attribute__((ns_returns_retained));
static id IFDefaultsSuite(id self __attribute__((ns_consumed)), SEL command, NSString *suite) {
    if ([suite hasPrefix:@"group."]) suite = [@"InstagramFocus." stringByAppendingString:suite];
    return IFOriginalDefaultsSuite(self, command, suite);
}

static CFDictionaryRef IFScopedKeychain(CFDictionaryRef query) CF_RETURNS_RETAINED;
static CFDictionaryRef IFScopedKeychain(CFDictionaryRef query) {
    NSMutableDictionary *copy = [(__bridge NSDictionary *)query mutableCopy];
    if (IFKeychainGroup) copy[(__bridge NSString *)kSecAttrAccessGroup] = IFKeychainGroup;
    return CFBridgingRetain(copy);
}

static OSStatus (*IFOriginalSecAdd)(CFDictionaryRef, CFTypeRef *);
static OSStatus (*IFOriginalSecCopy)(CFDictionaryRef, CFTypeRef *);
static OSStatus (*IFOriginalSecUpdate)(CFDictionaryRef, CFDictionaryRef);
static OSStatus (*IFOriginalSecDelete)(CFDictionaryRef);
static OSStatus IFKeychainAdd(CFDictionaryRef query, CFTypeRef *result) {
    if (!query) return errSecParam;
    CFDictionaryRef scoped = IFScopedKeychain(query);
    OSStatus code = IFOriginalSecAdd ? IFOriginalSecAdd(scoped, result) : errSecUnimplemented;
    CFRelease(scoped);
    return code;
}
static OSStatus IFKeychainCopy(CFDictionaryRef query, CFTypeRef *result) {
    if (!query) return errSecParam;
    CFDictionaryRef scoped = IFScopedKeychain(query);
    OSStatus code = IFOriginalSecCopy ? IFOriginalSecCopy(scoped, result) : errSecUnimplemented;
    CFRelease(scoped);
    return code;
}
static OSStatus IFKeychainUpdate(CFDictionaryRef query, CFDictionaryRef attributes) {
    if (!query) return errSecParam;
    CFDictionaryRef scoped = IFScopedKeychain(query);
    OSStatus code = IFOriginalSecUpdate ? IFOriginalSecUpdate(scoped, attributes) : errSecUnimplemented;
    CFRelease(scoped);
    return code;
}
static OSStatus IFKeychainDelete(CFDictionaryRef query) {
    if (!query) return errSecParam;
    CFDictionaryRef scoped = IFScopedKeychain(query);
    OSStatus code = IFOriginalSecDelete ? IFOriginalSecDelete(scoped) : errSecUnimplemented;
    CFRelease(scoped);
    return code;
}

__attribute__((constructor)) static void InstagramFocusInstall(void) {
    @autoreleasepool {
        IFKeychainGroup = [NSBundle.mainBundle objectForInfoDictionaryKey:@"InstagramFocusKeychainGroup"];
        IFHook(@"NSFileManager", @"containerURLForSecurityApplicationGroupIdentifier:", (IMP)IFGroupContainer, (IMP *)&IFOriginalGroupContainer, '@', 3);
        IFHook(@"NSUserDefaults", @"initWithSuiteName:", (IMP)IFDefaultsSuite, (IMP *)&IFOriginalDefaultsSuite, '@', 3);
        struct rebinding bindings[] = {
            {"SecItemAdd", IFKeychainAdd, (void **)&IFOriginalSecAdd},
            {"SecItemCopyMatching", IFKeychainCopy, (void **)&IFOriginalSecCopy},
            {"SecItemUpdate", IFKeychainUpdate, (void **)&IFOriginalSecUpdate},
            {"SecItemDelete", IFKeychainDelete, (void **)&IFOriginalSecDelete},
        };
        IFRecord(@"keychainRebindingResult", @(rebind_symbols(bindings, 4)));
        IFRecord(@"expectedInstagramVersion", @"418.2.0");
        IFRecord(@"focusPatchVersion", @2);
        IFRecord(@"actualInstagramVersion", [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"] ?: @"unknown");
        IFHook(@"IGUnifiedVideoCollectionView", @"setScrollEnabled:", (IMP)IFReelSetScroll, (IMP *)&IFOriginalReelSetScroll, 'v', 3);
        IFHook(@"IGUnifiedVideoCollectionView", @"isScrollEnabled", (IMP)IFReelIsScrollEnabled, &IFOriginalReelIsScrollEnabled, 'B', 2);
        IFHook(@"IGUnifiedVideoCollectionView", @"didMoveToWindow", (IMP)IFReelMove, (IMP *)&IFOriginalReelMove, 'v', 2);
        IFHook(@"_TtC19IGSundialAutoScroll19IGSundialAutoScroll", @"setIsEnabled:", (IMP)IFAutoScroll, (IMP *)&IFOriginalAutoScroll, 'v', 3);
        IFHook(@"IGTabBarController", @"viewDidLoad", (IMP)IFTabLoad, (IMP *)&IFOriginalTabLoad, 'v', 2);
        IFHook(@"IGTabBarControllerSwipeCoordinator", @"initWithSurfaces:parentViewController:enableHaptics:launcherSet:", (IMP)IFSwipeInit, (IMP *)&IFOriginalSwipeInit, '@', 6);
        IFHook(@"IGTabBarController", @"_layoutTabBar", (IMP)IFTabLayout, (IMP *)&IFOriginalTabLayout, 'v', 2);
        IFHook(@"IGTabBarController", @"_buttonForTabBarSurface:", (IMP)IFTabButton, (IMP *)&IFOriginalTabButton, '@', 3);
        IFHook(@"IGMainFeedListAdapterDataSource", @"objectsForListAdapter:", (IMP)IFHomeObjects, (IMP *)&IFOriginalHomeObjects, '@', 3);
        IFHook(@"IGExploreGridViewController", @"viewDidLoad", (IMP)IFExploreGridLoad, (IMP *)&IFOriginalExploreGridLoad, 'v', 2);
        IFHook(@"IGExploreViewController", @"viewDidLoad", (IMP)IFExploreLoad, (IMP *)&IFOriginalExploreLoad, 'v', 2);
    }
}
