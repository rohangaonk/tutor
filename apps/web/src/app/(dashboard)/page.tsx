import Link from "next/link";
import { Upload, MessageSquare, Trophy, TrendingUp, ArrowRight } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const features = [
  {
    href: "/upload",
    icon: Upload,
    title: "Upload Document",
    description:
      "Upload a PDF or DOCX and let Tutor chunk and embed it for instant Q&A and quiz generation.",
    cta: "Upload now",
    color: "text-blue-500",
    bg: "bg-blue-500/10",
  },
  {
    href: "/chat",
    icon: MessageSquare,
    title: "Chat with Document",
    description:
      "Ask any question about your uploaded material and receive grounded, streaming answers.",
    cta: "Start chatting",
    color: "text-violet-500",
    bg: "bg-violet-500/10",
  },
  {
    href: "/quiz",
    icon: Trophy,
    title: "Take a Quiz",
    description:
      "Challenge yourself with adaptive questions. Difficulty adjusts based on your performance.",
    cta: "Begin quiz",
    color: "text-amber-500",
    bg: "bg-amber-500/10",
  },
  {
    href: "/progress",
    icon: TrendingUp,
    title: "Track Progress",
    description:
      "Review your performance per topic and document — see where you're strong and what to improve.",
    cta: "View progress",
    color: "text-green-500",
    bg: "bg-green-500/10",
  },
];

export default function HomePage() {
  return (
    <div className="max-w-4xl w-full mx-auto space-y-8">
      {/* Hero */}
      <div className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Welcome to Tutor</h1>
        <p className="text-muted-foreground text-base max-w-xl">
          Upload a document, chat with it, quiz yourself, and track your learning — all powered by AI.
        </p>
      </div>

      {/* Feature cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {features.map(({ href, icon: Icon, title, description, cta, color, bg }) => (
          <Card key={href} className="group hover:shadow-md transition-shadow">
            <CardHeader className="pb-3">
              <div className={`inline-flex h-10 w-10 items-center justify-center rounded-lg ${bg} mb-1`}>
                <Icon className={`h-5 w-5 ${color}`} />
              </div>
              <CardTitle className="text-base">{title}</CardTitle>
              <CardDescription className="text-sm leading-relaxed">
                {description}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="ghost" size="sm" className="px-0 text-sm font-medium group-hover:text-primary transition-colors">
                <Link href={href}>
                  {cta}
                  <ArrowRight className="ml-1.5 h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Quick start */}
      <div className="rounded-xl border bg-muted/40 p-6 space-y-3">
        <h2 className="font-semibold">Quick start</h2>
        <ol className="space-y-1.5 text-sm text-muted-foreground list-decimal list-inside">
          <li>Upload a PDF or DOCX from the <strong className="text-foreground">Upload</strong> tab.</li>
          <li>Once processed, go to <strong className="text-foreground">Chat</strong> and ask questions about it.</li>
          <li>Test your understanding in the <strong className="text-foreground">Quiz</strong> tab with adaptive questions.</li>
          <li>Review your topic strengths in <strong className="text-foreground">Progress</strong>.</li>
        </ol>
      </div>
    </div>
  );
}



