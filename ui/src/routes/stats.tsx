import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function StatsPage() {
  return (
    <div className="p-6">
      <Card>
        <CardHeader>
          <CardTitle>Estatísticas</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Implementado na Onda 4.</p>
        </CardContent>
      </Card>
    </div>
  );
}
