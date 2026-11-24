# Ferlance on the phone

An Expo (React Native) app for the everyday jobs:

- **Today:** sales, costs and the change from last month, plus what to do next.
- **Debts:** new credit sales, recording payments, and WhatsApp or SMS reminders sent from your own phone.
- **Record:** paste MoMo messages, or photograph or type a notebook page and check every line before it's added.
- **Lance:** ask about your business in your own words.
- **Guides:** the same short videos and steps as the website. They open on the first sign-in.

Deeper work (invoices, stock, books, tax and payroll, reconciliation) stays on the website.

The app shares code with the website instead of copying it. These come straight from
`../frontend/src` (see `metro.config.js`):
- the guide text
- money and date formatting
- the debt reminder wording
- the API types

## Run it on your phone (free, no account)

1. Install **Expo Go** from the Play Store or the App Store.
2. On your computer:

   ```bash
   cd mobile && npm install && npx expo start
   ```

3. Scan the QR code with Expo Go (Android) or the Camera app (iPhone). Your phone and computer
   must be on the same Wi-Fi. If they can't be, use `npx expo start --tunnel`.

The app talks to the live server at `https://13-48-56-28.sslip.io` by default. To use another one,
tap **Use a different server** on the sign-in screen, or set `EXPO_PUBLIC_API_URL` before
`expo start`.

## Signing in and security

The app signs in through `/api/auth/mobile/*`:
- **Refresh token:** kept in the phone's secure store (Keychain on iPhone, Keystore on Android).
- **Access token:** kept only in memory.
- **Rotation:** every refresh swaps the refresh token for a new one.
- **Sessions:** phone sessions are separate from website sessions, and signing out ends them on the server.

## Publishing to the stores (later, paid)

Installing it as a real app, without Expo Go, needs a store build:
- **Google Play:** a one-off $25 developer account.
- **Apple App Store:** $99 a year.
- **Builds:** `npx eas-cli build` makes them, and needs a free Expo account.

Nothing here needs to change for that. `app.json` already sets the app name, the
`com.ferlance.app` identifiers and the permission messages.

## Checks

```bash
npx tsc --noEmit
```

```bash
npx expo-doctor
```

```bash
npx expo export --platform android
```
