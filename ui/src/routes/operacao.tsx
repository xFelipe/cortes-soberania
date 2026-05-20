import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function OperacaoPage() {
  return (
    <div className="p-6">
      <Card>
        <CardHeader>
          <CardTitle>Operação</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Pipeline, discover e canais — implementado na Onda 4.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
