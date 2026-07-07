export default function AuthLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="mb-8 flex items-center gap-2.5">
        <span
          className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-lg font-bold text-white"
          aria-hidden="true"
        >
          D
        </span>
        <span className="text-2xl font-semibold tracking-tight text-zinc-100">
          DocMind
        </span>
      </div>
      <div className="w-full max-w-sm">{children}</div>
    </div>
  );
}
