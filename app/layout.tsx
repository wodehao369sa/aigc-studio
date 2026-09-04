import "./globals.css";
import Link from "next/link";
export const metadata = { title: "AIGC Studio", description: "个人 AIGC 创作平台" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="zh-CN"><body><header><Link className="brand" href="/">AIGC Studio</Link><nav><Link href="/">创作</Link><Link href="/tasks">任务</Link><Link href="/settings">设置</Link></nav></header><main>{children}</main></body></html>; }
