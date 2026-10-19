/** Spinner and status text while a library page loads. */
export default function LibraryLoading({ label }: { label: string }) {
  return (
    <div role="status" className="mt-8 flex items-center gap-3 text-muted-foreground">
      <div aria-hidden="true" className="h-5 w-5 animate-spin rounded-full border-2 border-muted border-t-primary" />
      {label}
    </div>
  )
}
