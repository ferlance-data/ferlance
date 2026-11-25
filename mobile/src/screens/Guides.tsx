// The same guides as the website (frontend/src/lib/guides.ts): a short video of the real app,
// when to use the feature, why it helps, and the steps.

import { useVideoPlayer, VideoView } from 'expo-video';
import { useState } from 'react';
import { Pressable, View } from 'react-native';
import { GUIDE_LANGS, GUIDES, VOICE_CREDIT, guideScript, guideVideo, type Guide, type GuideLang } from '../../../frontend/src/lib/guides';
import { absolute } from '../api';
import { Body, Card, Screen, Segmented, Title, useTheme } from '../ui';

function Player({ guide, lang }: { guide: Guide; lang: GuideLang }) {
  const player = useVideoPlayer(absolute(guideVideo(guide.slug, lang)), (created) => {
    created.play();
  });
  return (
    <VideoView
      player={player}
      nativeControls
      contentFit="contain"
      style={{ width: '100%', maxWidth: 280, aspectRatio: 390 / 844, alignSelf: 'center', borderRadius: 14, backgroundColor: '#0f0f11' }}
      accessibilityLabel={`Video: ${guide.title}`}
    />
  );
}

function GuideCard({ guide, lang, open, onToggle }: { guide: Guide; lang: GuideLang; open: boolean; onToggle: () => void }) {
  const c = useTheme();
  return (
    <Card>
      <Pressable onPress={onToggle} accessibilityRole="button" accessibilityState={{ expanded: open }} style={{ gap: 4 }}>
        <Body style={{ fontWeight: '700', fontSize: 17 }}>{guide.title}</Body>
        <Body muted>{guide.when}</Body>
        <Body style={{ color: c.accent, fontWeight: '600' }}>{open ? 'Hide' : 'Watch and read'}</Body>
      </Pressable>
      {open ? (
        <View style={{ gap: 10 }}>
          {/* Keyed by language so switching starts the narrated file afresh. */}
          <Player key={lang} guide={guide} lang={lang} />
          <Body muted>
            {GUIDE_LANGS.find((item) => item.code === lang)?.draft ? 'The voice says (draft translation): ' : 'The voice says: '}
            {guideScript(guide.slug, lang)}
          </Body>
          <Body>
            <Body style={{ fontWeight: '600' }}>Why: </Body>
            {guide.why}
          </Body>
          {guide.steps.map((step, index) => (
            <Body key={step}>
              {index + 1}. {step}
            </Body>
          ))}
        </View>
      ) : null}
    </Card>
  );
}

export default function Guides() {
  const [open, setOpen] = useState<string | null>(GUIDES[0]?.slug ?? null);
  const [lang, setLang] = useState<GuideLang>('en');
  return (
    <Screen>
      <Title sub="Short videos of the real app with a voice in your language: when to use each feature, why, and how. Invoices and books are on the website.">
        Guides
      </Title>
      <Segmented value={lang} options={GUIDE_LANGS.map((item): [GuideLang, string] => [item.code, item.label])} onChange={setLang} />
      {GUIDES.map((guide) => (
        <GuideCard
          key={guide.slug}
          guide={guide}
          lang={lang}
          open={open === guide.slug}
          onToggle={() => setOpen(open === guide.slug ? null : guide.slug)}
        />
      ))}
      <Body muted>{VOICE_CREDIT}</Body>
    </Screen>
  );
}
