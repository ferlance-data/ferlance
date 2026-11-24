// Today at a glance: sales, profit and the change since last period, plus the top suggestions.

import { useCallback, useEffect, useState } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { money, percent } from '../../../frontend/src/lib/format';
import type { Analytics, InsightsResponse } from '../../../frontend/src/lib/types';
import { request } from '../api';
import { useSession } from '../session';
import { Body, Button, Card, Kpi, Loading, Notice, Title, useTheme } from '../ui';

/** The last 30 days; the server compares them with the 30 days before. */
function lastMonth(): string {
  const date = new Date(Date.now() - 30 * 86_400_000);
  return `?from=${date.toISOString().slice(0, 10)}`;
}

export default function Home() {
  const { business, path, signOut } = useSession();
  const c = useTheme();
  const [data, setData] = useState<{ analytics: Analytics; insights: InsightsResponse } | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const query = lastMonth();
      const [analytics, insights] = await Promise.all([
        request<Analytics>(path(`/analytics${query}`)),
        request<InsightsResponse>(path(`/insights${query}`)),
      ]);
      setData({ analytics, insights });
    } catch (failure) {
      setData(null);
      setError(failure instanceof Error ? failure.message : 'Could not load your numbers.');
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    void load();
  }, [load]);

  const kpis = data?.analytics.kpis;
  const change = data?.analytics.comparison.metrics?.total_revenue?.change_pct ?? null;
  const advice = data?.insights.advice;
  const top = advice ? advice.top.map((id) => advice.items.find((item) => item.id === id)).filter((item) => item !== undefined) : [];

  return (
    <ScrollView
      style={{ backgroundColor: c.bg }}
      contentContainerStyle={{ padding: 16, gap: 16, paddingBottom: 40 }}
      refreshControl={<RefreshControl refreshing={loading && !!data} onRefresh={() => void load()} />}
    >
      <Title sub="The last 30 days, compared with the 30 days before.">{business.name}</Title>
      {loading && !data ? <Loading /> : null}
      {error ? (
        <Card>
          <Notice text={error} error />
          <Body muted>If you have not added any records yet, paste MoMo messages or add a notebook page under Record.</Body>
        </Card>
      ) : null}
      {kpis ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <Kpi
            label="Sales"
            value={money(kpis.total_revenue, { compact: true, code: data.analytics.currency })}
            note={change === null ? 'No earlier period' : `${percent(change)} vs before`}
          />
          <Kpi label="Costs" value={money(kpis.total_cost, { compact: true, code: data.analytics.currency })} />
          <Kpi label="Sales made" value={String(kpis.transactions)} />
          <Kpi label="Best seller" value={kpis.top_product ?? '—'} />
        </View>
      ) : null}
      {top.length ? (
        <Card title="What to do next">
          {top.slice(0, 3).map((item) => (
            <View key={item.id} style={{ gap: 4 }}>
              <Body style={{ fontWeight: '600' }}>{item.title}</Body>
              <Body muted>{item.summary}</Body>
              {item.actions[0] ? <Body>→ {item.actions[0]}</Body> : null}
            </View>
          ))}
        </Card>
      ) : null}
      <Button label="Sign out" kind="ghost" onPress={signOut} />
    </ScrollView>
  );
}
