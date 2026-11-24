// The same guides as the website (frontend/src/lib/guides.ts): a short video of the real app,
// when to use the feature, why it helps, and the steps.

import { useVideoPlayer, VideoView } from 'expo-video';
import { useState } from 'react';
import { Pressable, View } from 'react-native';
import { GUIDES, type Guide } from '../../../frontend/src/lib/guides';
import { absolute } from '../api';
import { Body, Card, Screen, Title, useTheme } from '../ui';

function Player({ guide }: { guide: Guide }) {
  const player = useVideoPlayer(absolute(guide.video), (created) => {
    created.muted = true;
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

function GuideCard({ guide, open, onToggle }: { guide: Guide; open: boolean; onToggle: () => void }) {
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
          <Player guide={guide} />
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
  return (
    <Screen>
      <Title sub="Short videos of the real app: when to use each feature, why, and how. Some pages (invoices, stock, books) are on the website.">
        Guides
      </Title>
      {GUIDES.map((guide) => (
        <GuideCard
          key={guide.slug}
          guide={guide}
          open={open === guide.slug}
          onToggle={() => setOpen(open === guide.slug ? null : guide.slug)}
        />
      ))}
    </Screen>
  );
}
