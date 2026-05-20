import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/lib/theme";

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="p-6 max-w-md">
      <Card>
        <CardHeader>
          <CardTitle>Configurações</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium mb-2">Tema</p>
            <div className="flex gap-2">
              {(["system", "light", "dark"] as const).map((t) => (
                <Button
                  key={t}
                  variant={theme === t ? "default" : "outline"}
                  size="sm"
                  onClick={() => setTheme(t)}
                >
                  {t === "system" ? "Sistema" : t === "light" ? "Claro" : "Escuro"}
                </Button>
              ))}
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Tema atual: <strong>{theme}</strong>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
