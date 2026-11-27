#!/usr/bin/env bash
# Saves CloudWatch graphs as PNG into docs/img and prints per-minute numbers for the report.
# Run from the repository root after the load tests:  bash loadtest/export-graphs.sh [minutes-back]
set -euo pipefail
cd "$(dirname "$0")/.."

MIN="${1:-120}"
REGION="${AWS_REGION:-eu-north-1}"
TZ_OFFSET="+0200"
OUT=docs/img
mkdir -p "$OUT"

CLUSTER=library-cluster
SVC=library-svc
WORKER=library-worker-svc
ALB=$(aws elbv2 describe-load-balancers --region "$REGION" --names library-alb \
      --query 'LoadBalancers[0].LoadBalancerArn' --output text | tr -d '\r' | sed 's#.*:loadbalancer/##')
CACHE=$(aws elasticache describe-replication-groups --region "$REGION" --replication-group-id library-cache \
      --query 'ReplicationGroups[0].MemberClusters[0]' --output text | tr -d '\r')

widget() {  # name, json-metrics, title, extra-json
  local name="$1" metrics="$2" title="$3" extra="${4:-}"
  local json="{\"width\":1000,\"height\":400,\"start\":\"-PT${MIN}M\",\"timezone\":\"${TZ_OFFSET}\",\"region\":\"${REGION}\",\"period\":60,\"title\":\"${title}\",\"metrics\":${metrics}${extra}}"
  aws cloudwatch get-metric-widget-image --region "$REGION" --metric-widget "$json" \
      --output-format png --query MetricWidgetImage --output text | tr -d '\r\n' | base64 -d > "$OUT/$name.png"
  echo "saved $OUT/$name.png"
}

widget tasks "[[\"ECS/ContainerInsights\",\"DesiredTaskCount\",\"ClusterName\",\"$CLUSTER\",\"ServiceName\",\"$SVC\",{\"label\":\"Desired\"}],[\".\",\"RunningTaskCount\",\".\",\".\",\".\",\".\",{\"label\":\"Running\"}]]" \
  "API tasks: desired vs running" ",\"stat\":\"Maximum\",\"yAxis\":{\"left\":{\"min\":0,\"max\":5}}"

widget dashboard-autoscaling "[[\"AWS/ECS\",\"CPUUtilization\",\"ClusterName\",\"$CLUSTER\",\"ServiceName\",\"$SVC\",{\"stat\":\"Average\",\"label\":\"Average CPU %\"}]]" \
  "API CPU utilization, %" ",\"yAxis\":{\"left\":{\"min\":0,\"max\":100}},\"annotations\":{\"horizontal\":[{\"label\":\"Scaling target 60%\",\"value\":60},{\"label\":\"Alarm 70%\",\"value\":70,\"color\":\"#d62728\"}]}"

widget requests "[[\"AWS/ApplicationELB\",\"RequestCount\",\"LoadBalancer\",\"$ALB\",{\"stat\":\"Sum\",\"label\":\"Requests per minute\"}]]" \
  "Requests per minute"

widget latency "[[\"AWS/ApplicationELB\",\"TargetResponseTime\",\"LoadBalancer\",\"$ALB\",{\"stat\":\"p95\",\"label\":\"p95, s\"}]]" \
  "Latency p95, s"

widget db-load "[[\"AWS/RDS\",\"CPUUtilization\",\"DBInstanceIdentifier\",\"library-db\",{\"stat\":\"Average\",\"label\":\"RDS CPU %\"}],[\".\",\"DatabaseConnections\",\".\",\".\",{\"stat\":\"Average\",\"label\":\"Connections\",\"yAxis\":\"right\"}]]" \
  "Database load (RDS)"

widget dashboard-cache "[[\"AWS/ElastiCache\",\"CacheHits\",\"CacheClusterId\",\"$CACHE\",{\"stat\":\"Sum\",\"label\":\"Hits\"}],[\".\",\"CacheMisses\",\".\",\".\",{\"stat\":\"Sum\",\"label\":\"Misses\"}]]" \
  "Cache hits / misses per minute"

widget queue-messages "[[\"AWS/SQS\",\"ApproximateNumberOfMessagesVisible\",\"QueueName\",\"library-writes\",{\"stat\":\"Maximum\",\"label\":\"Waiting\"}],[\".\",\"ApproximateNumberOfMessagesNotVisible\",\".\",\".\",{\"stat\":\"Maximum\",\"label\":\"In flight\"}],[\".\",\"ApproximateNumberOfMessagesVisible\",\".\",\"library-writes-dlq\",{\"stat\":\"Maximum\",\"label\":\"DLQ\",\"color\":\"#d62728\"}]]" \
  "Queue: messages"

widget queue-workers "[[\"ECS/ContainerInsights\",\"DesiredTaskCount\",\"ClusterName\",\"$CLUSTER\",\"ServiceName\",\"$WORKER\",{\"label\":\"Desired\"}],[\".\",\"RunningTaskCount\",\".\",\".\",\".\",\".\",{\"label\":\"Running\"}]]" \
  "Worker tasks: desired vs running" ",\"stat\":\"Maximum\",\"yAxis\":{\"left\":{\"min\":0,\"max\":5}}"

widget queue-age "[[\"AWS/SQS\",\"ApproximateAgeOfOldestMessage\",\"QueueName\",\"library-writes\",{\"stat\":\"Maximum\",\"label\":\"Oldest message age, s\"}],[\".\",\"NumberOfMessagesSent\",\".\",\".\",{\"stat\":\"Sum\",\"label\":\"Sent/min\",\"yAxis\":\"right\"}],[\".\",\"NumberOfMessagesDeleted\",\".\",\".\",{\"stat\":\"Sum\",\"label\":\"Processed/min\",\"yAxis\":\"right\"}]]" \
  "Queue: age / throughput"

START=$(date -u -d "-${MIN} minutes" +%Y-%m-%dT%H:%M:%SZ)
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
stats() {  # namespace metric stat dims...
  local ns="$1" metric="$2" stat="$3"; shift 3
  aws cloudwatch get-metric-statistics --region "$REGION" --namespace "$ns" --metric-name "$metric" \
      --dimensions "$@" --start-time "$START" --end-time "$END" --period 60 --statistics "$stat" \
      --query "sort_by(Datapoints,&Timestamp)[].[Timestamp,$stat]" --output text
}
{
  echo "== API CPU % (UTC)";        stats AWS/ECS CPUUtilization Average Name=ClusterName,Value=$CLUSTER Name=ServiceName,Value=$SVC
  echo "== API running tasks";      stats ECS/ContainerInsights RunningTaskCount Maximum Name=ClusterName,Value=$CLUSTER Name=ServiceName,Value=$SVC
  echo "== RDS CPU %";              stats AWS/RDS CPUUtilization Maximum Name=DBInstanceIdentifier,Value=library-db
  echo "== Queue visible messages"; stats AWS/SQS ApproximateNumberOfMessagesVisible Maximum Name=QueueName,Value=library-writes
  echo "== Worker running tasks";   stats ECS/ContainerInsights RunningTaskCount Maximum Name=ClusterName,Value=$CLUSTER Name=ServiceName,Value=$WORKER
  echo "== DLQ visible";            stats AWS/SQS ApproximateNumberOfMessagesVisible Maximum Name=QueueName,Value=library-writes-dlq
} | tee loadtest/results/metrics.txt
echo "numbers saved to loadtest/results/metrics.txt"
