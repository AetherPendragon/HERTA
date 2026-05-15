import Container from "@/components/container";
import MetricCard from "./components/metric-card";

export interface MetricData {
  title: string;
  value: string;
  change: number;
}

export default function Metrics({ data }: { data: MetricData[] }) {
  return (
    <Container className="grid grid-cols-1 gap-y-6 border-b border-border py-4 phone:grid-cols-2 laptop:grid-cols-4">
      {data.map((metric) => (
        <MetricCard key={metric.title} {...metric} />
      ))}
    </Container>
  );
}
