import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

function fmt(usd: number) {
  return `$${usd.toFixed(2)}`;
}

export default function StatsPage() {
  const { data: summary = {} } = useQuery({
    queryKey: ["stats", "summary"],
    queryFn: api.stats.summary,
  });

  const { data: costs } = useQuery({
    queryKey: ["stats", "costs"],
    queryFn: api.stats.costs,
  });

  const { data: costsDetail = [] } = useQuery({
    queryKey: ["stats", "costsDetail"],
    queryFn: api.stats.costsDetail,
  });

  const { data: throughput = [] } = useQuery({
    queryKey: ["stats", "throughput"],
    queryFn: api.stats.throughput,
  });

  const { data: byCanal = [] } = useQuery({
    queryKey: ["stats", "byCanal"],
    queryFn: api.stats.byCanal,
  });

  // Custo projeção (extrapolação linear dos últimos 7 dias)
  const last7DaysCost = costsDetail
    .filter((r) => {
      const d = new Date(r.date);
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - 7);
      return d >= cutoff;
    })
    .reduce((acc, r) => acc + r.cost_usd, 0);
  const projectedMonthly = (last7DaysCost / 7) * 30;

  // Publicados
  const published =
    (summary["uploaded_youtube"] ?? 0) +
    (summary["scheduled_youtube"] ?? 0) +
    (summary["uploaded_tiktok"] ?? 0);

  // Taxa de aprovação (vídeos aprovados / (aprovados + rejeitados))
  const aprovados =
    (summary["approved_for_clips"] ?? 0) +
    (summary["finding_clips"] ?? 0) +
    (summary["clips_found"] ?? 0);
  const rejeitados =
    (summary["triage_metadata_rejected"] ?? 0) +
    (summary["triage_caption_rejected"] ?? 0) +
    (summary["triage_transcript_rejected"] ?? 0);
  const taxa = aprovados + rejeitados > 0
    ? Math.round((aprovados / (aprovados + rejeitados)) * 100)
    : null;

  // Throughput semanal para o gráfico
  const chartData = throughput.map((r) => ({
    semana: r.semana,
    Descobertos: r.videos_descobertos,
    "Clips criados": r.clips_criados,
    Publicados: r.clips_publicados,
  }));

  return (
    <div className="p-4 space-y-4">
      {/* 4 cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card>
          <CardHeader className="pb-1 pt-3">
            <CardTitle className="text-xs text-muted-foreground font-normal">
              Custo mês
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-2xl font-bold">{costs ? fmt(costs.total_usd) : "—"}</p>
            <p className="text-xs text-muted-foreground">
              Projeção: {fmt(projectedMonthly)}/mês
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-1 pt-3">
            <CardTitle className="text-xs text-muted-foreground font-normal">
              Throughput (últ. 4 sem.)
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-2xl font-bold">
              {throughput.reduce((a, r) => a + r.clips_criados, 0)}
            </p>
            <p className="text-xs text-muted-foreground">clips criados</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-1 pt-3">
            <CardTitle className="text-xs text-muted-foreground font-normal">
              Publicados
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-2xl font-bold">{published}</p>
            <p className="text-xs text-muted-foreground">clips no ar</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-1 pt-3">
            <CardTitle className="text-xs text-muted-foreground font-normal">
              Taxa de aprovação
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-2xl font-bold">{taxa !== null ? `${taxa}%` : "—"}</p>
            <p className="text-xs text-muted-foreground">
              {aprovados}v / {aprovados + rejeitados}v
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Bar chart 4 semanas */}
      {chartData.length > 0 && (
        <Card>
          <CardHeader className="pb-2 pt-3">
            <CardTitle className="text-sm">Throughput semanal (últimas 4 semanas)</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData} margin={{ top: 0, right: 8, left: -16, bottom: 0 }}>
                <XAxis dataKey="semana" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="Descobertos" fill="#6366f1" />
                <Bar dataKey="Clips criados" fill="#22c55e" />
                <Bar dataKey="Publicados" fill="#f59e0b" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Tabela por canal */}
      {byCanal.length > 0 && (
        <Card>
          <CardHeader className="pb-2 pt-3">
            <CardTitle className="text-sm">Por canal</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-xs text-muted-foreground uppercase">
                <tr>
                  <th className="text-left px-4 py-2">Canal</th>
                  <th className="text-right px-4 py-2">Vídeos</th>
                  <th className="text-right px-4 py-2">Aprovados</th>
                  <th className="text-right px-4 py-2">Clips</th>
                  <th className="text-right px-4 py-2">Publicados</th>
                </tr>
              </thead>
              <tbody>
                {byCanal.map((row) => (
                  <tr key={row.canal_id} className="border-t">
                    <td className="px-4 py-2 font-mono text-xs">{row.canal_id}</td>
                    <td className="px-4 py-2 text-right">{row.total_videos}</td>
                    <td className="px-4 py-2 text-right">{row.videos_aprovados}</td>
                    <td className="px-4 py-2 text-right">{row.clips_gerados}</td>
                    <td className="px-4 py-2 text-right">{row.clips_publicados}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {byCanal.length === 0 && chartData.length === 0 && (
        <p className="text-center text-muted-foreground py-16">
          Nenhum dado disponível ainda.
        </p>
      )}
    </div>
  );
}
