import * as React from "react";
import * as Cmdk from "cmdk";
import { Search, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

const Command = React.forwardRef<
  HTMLElement,
  React.ComponentProps<typeof Cmdk.CommandRoot>
>(
  ({ className, ...props }, ref) => (
    <Cmdk.CommandRoot
      ref={ref}
      className={cn("w-full min-w-[225px]", className)}
      {...props}
    />
  )
);
Command.displayName = "Command";

const CommandGroup = React.forwardRef<
  HTMLElement,
  React.ComponentProps<typeof Cmdk.CommandGroup>
>(
  ({ className, ...props }, ref) => (
    <Cmdk.CommandGroup
      ref={ref}
      className={cn("overflow-y-auto overflow-x-hidden h-full w-full", className)}
      {...props}
    />
  )
);
CommandGroup.displayName = "CommandGroup";

const CommandInput = React.forwardRef<
  HTMLElement,
  React.ComponentProps<typeof Cmdk.CommandInput>
>(
  ({ className, ...props }, ref) => (
    <Cmdk.CommandInput
      ref={ref}
      className={cn("w-full py-2 text-sm", className)}
      {...props}
    />
  )
);
CommandInput.displayName = "CommandInput";

const CommandItem = React.forwardRef<
  HTMLElement,
  React.ComponentProps<typeof Cmdk.CommandItem>
>(
  ({ className, children, ...props }, ref) => (
    <Cmdk.CommandItem
      ref={ref}
      className={cn(
        "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className
      )}
      {...props}
    >
      {children}
    </Cmdk.CommandItem>
  )
);
CommandItem.displayName = "CommandItem";

const CommandItemIndicator = React.forwardRef<
  HTMLElement,
  React.HTMLAttributes<HTMLSpanElement>
>(
  ({ className, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(
        "absolute left-2 flex h-3.5 w-3.5 items-center justify-center",
        className
      )}
      {...props}
    />
  )
);
CommandItemIndicator.displayName = "CommandItemIndicator";

const CommandList = React.forwardRef<
  HTMLElement,
  React.ComponentProps<typeof Cmdk.CommandList>
>(
  ({ className, ...props }, ref) => (
    <Cmdk.CommandList
      ref={ref}
      className={cn("overflow-y-auto overflow-x-hidden h-full w-full", className)}
      {...props}
    />
  )
);
CommandList.displayName = "CommandList";

const CommandSeparator = React.forwardRef<
  HTMLElement,
  React.HTMLAttributes<HTMLHRElement>
>(
  ({ className, ...props }, ref) => (
    <hr
      ref={ref}
      className={cn("border-border mx-1 my-0 shrink-0", className)}
      {...props}
    />
  )
);
CommandSeparator.displayName = "CommandSeparator";

const CommandEmpty2 = React.forwardRef<
  HTMLElement,
  React.HTMLAttributes<HTMLDivElement>
>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("py-6 text-center text-sm", className)} {...props} />
  )
);
CommandEmpty2.displayName = "CommandEmpty";

export {
  Command,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandItemIndicator,
  CommandList,
  CommandSeparator,
  CommandEmpty2 as CommandEmpty,
  Search,
  ChevronRight,
};
