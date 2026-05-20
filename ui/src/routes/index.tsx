import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function InboxPage() {
  return (
    <div className="p-6">
      <Card>
        <CardHeader>
          <CardTitle>Inbox</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Implementado na Onda 4.</p>
        </CardContent>
      </Card>
    </div>
  );
}
