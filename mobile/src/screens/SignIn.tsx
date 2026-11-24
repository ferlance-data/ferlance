import { useState } from 'react';
import { KeyboardAvoidingView, Platform, View } from 'react-native';
import type { Business } from '../../../frontend/src/lib/types';
import { DEFAULT_SERVER, signIn } from '../api';
import { Body, Button, Field, Notice, Screen, Title } from '../ui';

export default function SignIn({ onSignedIn, message }: { onSignedIn: (business: Business | null) => void; message?: string }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [server, setServer] = useState(DEFAULT_SERVER);
  const [showServer, setShowServer] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(message ?? '');

  const submit = async () => {
    if (!email.trim() || !password) {
      setError('Enter your email and password.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      onSignedIn(await signIn(server, email.trim(), password));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not sign in.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen>
        <View style={{ height: 24 }} />
        <Title sub="Sign in with the account you made on the Ferlance website.">Ferlance</Title>
        <Field
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          textContentType="username"
        />
        <Field
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="password"
          textContentType="password"
          onSubmitEditing={() => void submit()}
        />
        {error ? <Notice text={error} error /> : null}
        <Button label="Sign in" onPress={() => void submit()} busy={busy} />
        {showServer ? (
          <Field
            label="Server address"
            value={server}
            onChangeText={setServer}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />
        ) : (
          <Button label="Use a different server" kind="ghost" onPress={() => setShowServer(true)} />
        )}
        <Body muted>New to Ferlance? Create your workspace on the website first, then sign in here.</Body>
      </Screen>
    </KeyboardAvoidingView>
  );
}
