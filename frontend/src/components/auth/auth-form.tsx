"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import type { UserOut } from "@/lib/api-types";
import { api, isApiClientError } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const ERROR_MESSAGES: Record<string, string> = {
  email_taken: "An account with this email already exists. Try logging in.",
  invalid_credentials: "Incorrect email or password.",
  rate_limited: "Too many attempts. Please wait a moment and try again.",
  validation_error: "Please check your email and password and try again.",
};

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{
    email?: string;
    password?: string;
  }>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isLogin = mode === "login";

  const validate = (): boolean => {
    const errors: { email?: string; password?: string } = {};
    if (!EMAIL_PATTERN.test(email.trim())) {
      errors.email = "Enter a valid email address.";
    }
    if (password.length === 0) {
      errors.password = "Enter your password.";
    } else if (!isLogin && password.length < 8) {
      errors.password = "Password must be at least 8 characters.";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setApiError(null);
    if (!validate()) return;
    setSubmitting(true);
    try {
      await api.post<UserOut>(`/api/auth/${isLogin ? "login" : "register"}`, {
        email: email.trim(),
        password,
      });
      router.replace("/documents");
    } catch (err) {
      if (isApiClientError(err)) {
        setApiError(ERROR_MESSAGES[err.code] ?? err.detail);
      } else {
        setApiError("Something went wrong. Please try again.");
      }
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="p-6">
          <h1 className="text-lg font-semibold text-zinc-100">
            {isLogin ? "Welcome back" : "Create your account"}
          </h1>
          <p className="mt-1 text-sm text-zinc-400">
            {isLogin
              ? "Log in to chat with your documents."
              : "Upload documents and ask questions with cited answers."}
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none transition-colors focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                placeholder="you@example.com"
              />
              {fieldErrors.email && (
                <p className="mt-1 text-xs text-red-400">{fieldErrors.email}</p>
              )}
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-xs font-medium text-zinc-300"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete={isLogin ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none transition-colors focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                placeholder={isLogin ? "Your password" : "At least 8 characters"}
              />
              {fieldErrors.password && (
                <p className="mt-1 text-xs text-red-400">
                  {fieldErrors.password}
                </p>
              )}
            </div>

            {apiError && (
              <div
                role="alert"
                className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300"
              >
                {apiError}
              </div>
            )}

            <Button type="submit" loading={submitting} className="w-full">
              {isLogin ? "Log in" : "Create account"}
            </Button>
          </form>

          <p className="mt-5 text-center text-xs text-zinc-500">
            {isLogin ? (
              <>
                No account yet?{" "}
                <Link
                  href="/register"
                  className="font-medium text-indigo-400 hover:text-indigo-300"
                >
                  Create one
                </Link>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <Link
                  href="/login"
                  className="font-medium text-indigo-400 hover:text-indigo-300"
                >
                  Log in
                </Link>
              </>
            )}
          </p>
        </CardBody>
      </Card>

      {isLogin && (
        <Card className="border-indigo-500/20 bg-indigo-500/5">
          <CardBody className="px-5 py-3">
            <p className="text-xs text-zinc-400">
              <span className="font-medium text-indigo-300">Demo account:</span>{" "}
              demo@docmind.dev / demo1234
            </p>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
