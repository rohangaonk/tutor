import NavBar from "@/components/layout/NavBar";
import AuthGuard from "@/components/layout/AuthGuard";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <NavBar />
      <main className="flex-1 flex flex-col">{children}</main>
    </AuthGuard>
  );
}
