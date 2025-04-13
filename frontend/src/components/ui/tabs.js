import { cn } from "../../lib/utils"

function Tabs({ children, className, ...props }) {
  return (
    <div className={cn("w-full", className)} {...props}>
      {children}
    </div>
  )
}

function TabsList({ children, className, ...props }) {
  return (
    <div
      className={cn(
        "inline-flex items-center justify-center rounded-md bg-gray-100 p-1 mb-4",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

function TabsTrigger({ children, value, activeValue, onSelect, className, ...props }) {
  const isActive = activeValue === value

  return (
    <button
      type="button"
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
        isActive
          ? "bg-white text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground hover:bg-gray-200",
        className
      )}
      onClick={() => onSelect(value)}
      {...props}
    >
      {children}
    </button>
  )
}

function TabsContent({ children, value, activeValue, className, ...props }) {
  const isActive = activeValue === value

  if (!isActive) return null

  return (
    <div
      className={cn(
        "mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent }