"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navigations } from "@/config/site";
import { cn } from "@/lib/utils";

export default function Navigation() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-grow flex-col gap-y-1 p-2">
      {navigations.map((navigation) => {
        const Icon = navigation.icon;
        const isActive = pathname === navigation.href || (navigation.href !== "/" && pathname.startsWith(navigation.href));
        return (
          <Link
            key={navigation.name}
            href={navigation.href}
            className={cn(
              "flex items-center rounded-md px-2 py-1.5 hover:bg-slate-200 dark:hover:bg-slate-800",
              isActive ? "bg-primary/10 text-primary dark:bg-primary/20" : "bg-transparent text-muted-foreground",
            )}
          >
            <Icon size={16} className={cn("mr-2", isActive && "text-primary")} />
            <span className="text-sm">{navigation.name}</span>
          </Link>
        );
      })}
    </nav>
  );
}
