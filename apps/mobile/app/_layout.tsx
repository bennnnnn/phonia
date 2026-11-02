import "@/lib/i18n";

import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { InteractionManager, StyleSheet } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { useTranslation } from "react-i18next";

import { AuthProvider } from "@/contexts/AuthContext";
import { AiConsentRedirect } from "@/features/auth/components/AiConsentRedirect";
import { ActionFeedbackProvider } from "@/contexts/ActionFeedbackContext";
import { AppearanceProvider } from "@/contexts/AppearanceContext";
import { ModelsProvider } from "@/contexts/ModelsContext";
import { NetworkProvider, useNetwork } from "@/contexts/NetworkContext";
import { TodosProvider } from "@/features/todos/context/TodosContext";
import { PushNotificationBootstrap } from "@/features/todos/components/PushNotificationBootstrap";
import { OfflineBanner } from "@/components/OfflineBanner";
import { stackBackOptions } from "@/ui/controls/StackBackButton";
import { DialogHost } from "@/ui/overlay/DialogHost";
import { preloadSimulationSizing } from "@/components/rich/LazyHeavyRich";
import { useLaunchFonts } from "@/hooks/useLaunchFonts";
import { sweepOldPickerCopies } from "@/lib/accountFiles";
import { watchPhoneClock } from "@/lib/datetime/phoneClockSync";
import { restoreLaunchPrefs } from "@/lib/launchPrefs";
import { markLaunchReady } from "@/lib/launchSplash";
import { useReduceMotion } from "@/lib/reduceMotion";
import { useStackHeaderOptions } from "@/lib/stackHeader";
import {
  stackAuthTransition,
  stackHomeTransition,
  stackPushTransition,
  stackUtilityTransition,
} from "@/lib/stackTransitions";
import { initMobileSentry } from "@/lib/sentry";
import { useTheme } from "@/lib/theme";

// Before the first render: the user's appearance, accent and language.
void restoreLaunchPrefs().then(() => markLaunchReady("prefs"));
// Before anything can be picked, so a fresh pick is never in the listing.
void sweepOldPickerCopies();

const markSessionRestored = () => markLaunchReady("session");

function RootNavigator() {
  const { t } = useTranslation();
  const theme = useTheme();
  const header = useStackHeaderOptions();
  const { status } = useNetwork();
  const reduceMotion = useReduceMotion();

  return (
    <>
      <StatusBar style={theme.isDark ? "light" : "dark"} />
      <OfflineBanner status={status} />
      <Stack
        screenOptions={{
          ...stackPushTransition(reduceMotion),
          headerShown: false,
          contentStyle: { backgroundColor: theme.bg },
        }}
      >
        <Stack.Screen name="login" options={stackAuthTransition(reduceMotion)} />
        <Stack.Screen name="onboarding" options={stackAuthTransition(reduceMotion)} />
        <Stack.Screen name="consent" options={stackAuthTransition(reduceMotion)} />
        <Stack.Screen
          name="index"
          options={{ ...stackHomeTransition(), title: "", headerShown: false }}
        />
        <Stack.Screen
          name="memory"
          options={{ ...stackUtilityTransition(reduceMotion), headerShown: false }}
        />
        <Stack.Screen
          name="settings"
          options={{ ...stackPushTransition(reduceMotion), headerShown: false }}
        />
        <Stack.Screen
          name="todos"
          options={{
            ...stackUtilityTransition(reduceMotion),
            ...header,
            headerShown: true,
            title: t("drawer.reminders"),
            headerBackVisible: false,
            ...stackBackOptions(),
          }}
        />
        <Stack.Screen
          name="gallery"
          options={{
            ...stackUtilityTransition(reduceMotion),
            ...header,
            headerShown: true,
            title: t("gallery.title"),
            headerBackVisible: false,
            headerRight: undefined,
            ...stackBackOptions(),
          }}
        />
      </Stack>
    </>
  );
}

export default function RootLayout() {
  const fontsReady = useLaunchFonts();

  // Dates follow the phone's zone and 12/24-hour setting as they change.
  useEffect(() => watchPhoneClock(), []);

  // Work for later in the session, once the launch has settled.
  useEffect(() => {
    const task = InteractionManager.runAfterInteractions(() => {
      void initMobileSentry();
      preloadSimulationSizing();
    });
    return () => task.cancel();
  }, []);

  return (
    <GestureHandlerRootView style={styles.root}>
      <AppearanceProvider>
        <ActionFeedbackProvider>
          <AuthProvider onRestored={markSessionRestored}>
            {fontsReady ? (
              <ModelsProvider>
                <TodosProvider>
                  <NetworkProvider>
                    <PushNotificationBootstrap />
                    <AiConsentRedirect />
                    <RootNavigator />
                    <DialogHost />
                  </NetworkProvider>
                </TodosProvider>
              </ModelsProvider>
            ) : null}
          </AuthProvider>
        </ActionFeedbackProvider>
      </AppearanceProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});

/**
 * A crash no screen or section caught (the chat, the sign-in flow, or this
 * layout itself) shows the shared error view in place of the whole app.
 */
export { ScreenErrorBoundary as ErrorBoundary } from "@/components/ScreenErrorBoundary";
