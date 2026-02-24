import { getViewComponent } from "../app/routeViews";
import type { AppRoute } from "../app/routeTypes";

interface ViewHostProps {
  route: AppRoute;
}

export default function ViewHost({ route }: ViewHostProps) {
  const ViewComponent = getViewComponent(route.name);
  return (
    <div className="view-host" id="view-container">
      <ViewComponent route={route} />
    </div>
  );
}
