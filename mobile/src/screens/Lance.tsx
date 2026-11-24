// Ask Lance: plain-language questions answered from the business's own records.

import { useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, View, type ScrollViewInstance } from 'react-native';
import { request } from '../api';
import { useSession } from '../session';
import { Body, Button, Field, Notice, Title, useTheme } from '../ui';

interface Turn {
  role: 'user' | 'assistant';
  text: string;
}

const STARTERS = ['How did sales go this week?', 'Which products make the most profit?', 'What should I restock?'];

/** Lance answers in light Markdown; show it as plain text on the phone. */
const plain = (text: string): string =>
  text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/^\s*[-*]\s+/gm, '• ');

export default function Lance() {
  const { path } = useSession();
  const c = useTheme();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const conversation = useRef<string | null>(null);
  const scroller = useRef<ScrollViewInstance>(null);

  const ask = async (text: string) => {
    const asked = text.trim();
    if (!asked || busy) return;
    setTurns((current) => [...current, { role: 'user', text: asked }]);
    setQuestion('');
    setBusy(true);
    setError('');
    try {
      const result = await request<{ conversation_id: string; answer: string }>(path('/ask-lance'), {
        body: { question: asked, conversation_id: conversation.current },
      });
      conversation.current = result.conversation_id;
      setTurns((current) => [...current, { role: 'assistant', text: plain(result.answer) }]);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Lance could not answer just now.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        ref={scroller}
        contentContainerStyle={{ padding: 16, gap: 12 }}
        onContentSizeChange={() => scroller.current?.scrollToEnd({ animated: true })}
        keyboardShouldPersistTaps="handled"
      >
        <Title sub="Ask about your business in your own words. Lance answers from your records and says when something is missing.">
          Ask Lance
        </Title>
        {turns.length === 0
          ? STARTERS.map((starter) => <Button key={starter} label={starter} kind="secondary" onPress={() => void ask(starter)} />)
          : null}
        {turns.map((turn, index) => (
          <View
            key={index}
            style={{
              alignSelf: turn.role === 'user' ? 'flex-end' : 'stretch',
              maxWidth: turn.role === 'user' ? '85%' : '100%',
              backgroundColor: turn.role === 'user' ? c.accent : c.surface,
              borderColor: c.border,
              borderWidth: turn.role === 'user' ? 0 : 1,
              borderRadius: 14,
              padding: 12,
            }}
          >
            <Text selectable style={{ color: turn.role === 'user' ? c.accentText : c.text, fontSize: 15, lineHeight: 22 }}>
              {turn.text}
            </Text>
          </View>
        ))}
        {busy ? <Body muted>Lance is looking at your records…</Body> : null}
        {error ? <Notice text={error} error /> : null}
      </ScrollView>
      <View style={{ padding: 12, gap: 8, borderTopWidth: 1, borderColor: c.border, backgroundColor: c.bg }}>
        <Field
          label="Your question"
          value={question}
          onChangeText={setQuestion}
          placeholder="e.g. Who owes me the most?"
          returnKeyType="send"
          onSubmitEditing={() => void ask(question)}
        />
        <Button label="Ask" onPress={() => void ask(question)} busy={busy} disabled={!question.trim()} />
      </View>
    </KeyboardAvoidingView>
  );
}
