/**
 * Renders the offline / service-down error route. It is a placeholder screen backed by
 * PlaceholderLayout, standing in for the not-yet-built content described in UX spec section 22.
 */
import { PlaceholderLayout } from '@/components/layout/PlaceholderLayout';

export default function OfflinePage() {
  return (
    <PlaceholderLayout title="Offline" uxSpecSection="§22 Error: Offline / Service Down" />
  );
}
