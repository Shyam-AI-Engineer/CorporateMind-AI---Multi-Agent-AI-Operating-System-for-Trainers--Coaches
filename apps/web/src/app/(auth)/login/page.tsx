export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-md space-y-8 px-4">
        <div className="text-center">
          <h1 className="text-3xl font-bold tracking-tight">CorporateMind AI</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign in to your account
          </p>
        </div>
        {/* TODO(Phase 1): LoginForm component */}
        <div className="rounded-lg border bg-card p-8 shadow-sm">
          <p className="text-center text-muted-foreground">Login form coming in Phase 1</p>
        </div>
      </div>
    </main>
  );
}
