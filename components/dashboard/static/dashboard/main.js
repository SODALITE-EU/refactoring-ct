url = window.location;
host = url.hostname;
protocol = url.protocol
host_orchestrator = protocol + "//" + host + ":5000";
host_containers = protocol + "//" + host + ":5001";
host_requests = protocol + "//" + host + ":5002";
host_controller = protocol + "//" + host + ":5003";
host_dispatcher = protocol + "//" + host + ":8000";

function deviceFormatter(data) {
  return data === 0 ? "CPU" : "GPU";
}

function floatFormatter(data) {
  return data == null ? null : data.toFixed(6);
}

function containerIdFormatter(data) {
  return data == null ? null : data.slice(0, 12);
}

function responseFormatter(data) {
  return data != null && data.length > 200 ? data.slice(0, 200) + "..." : data;
}

function jsonFormatter(data) {
  return JSON.stringify(data, null, 2);
}

function stateFormatter(data) {
  if (data === 0) return "CREATED";
  if (data === 1) return "WAITING";
  if (data === 2) return "COMPLETED";
  if (data === 3) return "ERROR";
}

function deviceFormatter(data) {
  if (data === null) return data;
  if (data === 0) return "CPU";
  if (data === 1) return "GPU";
}

function resetRequestsStore() {
  $.ajax({
    url: host_requests + "/requests",
    type: "DELETE",
    success: function (result) {},
  });
}

// Status
function refreshStatus(){
  $.get(host_orchestrator + "/", function (data) {
    $("#orchestrator-status").text(data["status"])
  }).fail(function() {
    $("#orchestrator-status").text("?")
  });

  $.get(host_containers + "/", function (data) {
    $("#containers-manager-status").text(data["status"])
  }).fail(function() {
    $("#containers-manager-status").text("?")
  });

  $.get(host_requests + "/", function (data) {
    $("#requests-store-status").text(data["status"])
  }).fail(function() {
    $("#requests-store-status").text("?")
  });

  $.get(host_controller + "/", function (data) {
    $("#controller-status").text(data["status"])
  }).fail(function() {
    $("#controller-status").text("?")
  });

  $.get(host_dispatcher + "/", function (data) {
    $("#dispatcher-status").text(data["status"])
  }).fail(function() {
    $("#dispatcher-status").text("?")
  });
}
refreshStatus()
// END Status

// Configuration
function refreshConfiguration(){
  $.get(host_orchestrator + "/configuration/tfs", function (data) {
    $("#tfs-config").val(data["configuration"])
  }).fail(function() {
    $("#tfs-config").val("?")
  });

  $.get(host_orchestrator + "/configuration/k8s/deployment", function (data) {
    $("#k8s-deployment").val(data["configuration"])
  }).fail(function() {
    $("#k8s-deployment").val("?")
  });

  $.get(host_orchestrator + "/configuration/k8s/service", function (data) {
    $("#k8s-service").val(data["configuration"])
  }).fail(function() {
    $("#k8s-service").val("?")
  });

  $.get(host_requests + "/configuration", function (data) {
    $("#request-store").val(JSON.stringify(data["configuration"], undefined, 4))
  }).fail(function(data) {
    $("#request-store").val("?")
  });

  $.get(host_controller + "/configuration", function (data) {
    $("#controller").val(JSON.stringify(data["configuration"], undefined, 4))
  }).fail(function(data) {
    $("#controller").val("?")
  });

  $.get(host_containers + "/configuration", function (data) {
    $("#containers-manager").val(JSON.stringify(data["configuration"], undefined, 4))
  }).fail(function(data) {
    $("#containers-manager").val("?")
  });

  $.get(host_dispatcher + "/configuration", function (data) {
    $("#dispatcher").val(JSON.stringify(data["configuration"], undefined, 4))
  }).fail(function(data) {
    $("#dispatcher").val("?")
  });
}
refreshConfiguration()
// END Configuration

if($("#table-controller-log").length){
  $("#table-controller-log").bootstrapTable({
  autoRefresh: true,
  autoRefreshInterval: 3,
  url: host_controller + "/logs",
  pagination: true,
  search: true,
  columns: [
    {
      field: "ts",
      title: "ts",
      sortable: true,
    },
    {
      field: "date",
      title: "date",
      sortable: true,
    },
    {
      field: "type",
      title: "type",
      sortable: true,
    },
    {
      field: "logs",
      title: "logs",
      formatter: jsonFormatter,
      sortable: false,
    },
  ],
});
}

if($("#table-models").length) {
  $("#table-models").bootstrapTable({
    autoRefresh: true,
    autoRefreshInterval: 10,
    url: host_containers + "/models",
    pagination: false,
    search: true,
    columns: [
      {
        field: "name",
        title: "name",
        sortable: true,
      },
      {
        field: "version",
        title: "version",
        sortable: true,
      },
      {
        field: "sla",
        title: "sla",
        sortable: true,
      },
      {
        field: "alpha",
        title: "alpha",
        sortable: true,
      },
      {
        field: "profiled_rt",
        title: "profiled_rt",
        sortable: true,
      },
    ],
  });
}

if($("#table-containers").length) {
  $("#table-containers").bootstrapTable({
    autoRefresh: true,
    autoRefreshInterval: 10,
    url: host_containers + "/containers",
    pagination: false,
    search: true,
    columns: [
      {
        field: "model",
        title: "model",
        sortable: true,
      },
      {
        field: "container",
        title: "container",
        sortable: true,
      },
      {
        field: "container_id",
        title: "container_id",
        formatter: containerIdFormatter,
        sortable: true,
      },
      {
        field: "version",
        title: "version",
        sortable: true,
      },
      {
        field: "active",
        title: "active",
        sortable: true,
      },
      {
        field: "device",
        title: "device",
        formatter: deviceFormatter,
        sortable: true,
      },
      {
        field: "node",
        title: "node",
        sortable: true,
      },
      {
        field: "port",
        title: "port",
        sortable: true,
      },
      {
        field: "endpoint",
        title: "endpoint",
        sortable: true,
      },
      {
        field: "quota",
        title: "quota",
        sortable: true,
      },
    ],
  });
}

if($("#table-requests").length) {
  $("#table-requests").bootstrapTable({
    autoRefresh: true,
    autoRefreshInterval: 10,
    url: host_requests + "/requests?max_reqs=300",
    pagination: true,
    search: true,
    columns: [
      {
        field: "id",
        title: "id",
        sortable: true,
      },
      {
        field: "model",
        title: "model",
        sortable: true,
      },
      {
        field: "version",
        title: "version",
        sortable: true,
      },
      {
        field: "node",
        title: "node",
        sortable: true,
      },
      {
        field: "container",
        title: "container",
        sortable: true,
      },
      {
        field: "device",
        title: "device",
        sortable: true,
        formatter: deviceFormatter,
      },
      {
        field: "instances",
        title: "instances",
      },
      {
        field: "state",
        formatter: stateFormatter,
        title: "state",
      },
      {
        field: "response",
        title: "response",
        formatter: responseFormatter,
      },
      {
        field: "ts_in",
        title: "ts_in",
        sortable: true,
      },
      {
        field: "ts_out",
        title: "ts_out",
        sortable: true,
      },
      {
        field: "process_time",
        title: "process_time",
        formatter: floatFormatter,
        sortable: true,
      },
      {
        field: "resp_time",
        title: "resp_time",
        formatter: floatFormatter,
        sortable: true,
      },
    ],
  });
}

if($("#table-metrics-model").length) {
  $("#table-metrics-model").bootstrapTable({
    autoRefresh: true,
    autoRefreshInterval: 3,
    url: host_requests + "/metrics/model",
    pagination: false,
    search: false,
    columns: [
      {
        field: "model",
        title: "model",
        sortable: true,
      },
      {
        field: "version",
        title: "version",
        sortable: true,
      },
      {
        field: "metrics.completed",
        title: "metrics.completed",
        sortable: true,
      },
      {
        field: "metrics.input_reqs",
        title: "metrics.input_reqs",
        sortable: true,
      },
      {
        field: "metrics.created",
        title: "metrics.created",
        sortable: true,
      },
      {
        field: "metrics.on_gpu",
        title: "metrics.on_gpu",
        sortable: true,
      },
      {
        field: "metrics.on_cpu",
        title: "metrics.on_cpu",
        sortable: true,
      },
      {
        field: "metrics.avg",
        title: "metrics.avg",
        formatter: floatFormatter,
        sortable: true,
      },
      {
        field: "metrics.avg_process",
        title: "metrics.avg_process",
        formatter: floatFormatter,
        sortable: true,
      },
      {
        field: "metrics.dev",
        title: "metrics.dev",
        formatter: floatFormatter,
        sortable: true,
      },
      {
        field: "metrics.min",
        title: "metrics.min",
        formatter: floatFormatter,
        sortable: true,
      },
      {
        field: "metrics.max",
        title: "metrics.max",
        formatter: floatFormatter,
        sortable: true,
      },
    ],
  });
}

if($("#table-metrics-container").length) {
  $("#table-metrics-container").bootstrapTable({
    autoRefresh: true,
    autoRefreshInterval: 3,
    url: host_requests + "/metrics/container",
    pagination: false,
    search: false,
    columns: [
      {
        field: "container.container",
        title: "container.container",
        sortable: true,
      },
      {
        field: "container.model",
        title: "container.model",
        sortable: true,
      },
      {
        field: "container.node",
        title: "container.node",
        sortable: true,
      },
      {
        field: "metrics.completed",
        title: "metrics.completed",
        sortable: true,
      },
      {
        field: "metrics.input_reqs",
        title: "metrics.input_reqs",
        sortable: true,
      },
      {
        field: "metrics.created",
        title: "metrics.created",
        sortable: true,
      },
      {
        field: "metrics.on_gpu",
        title: "metrics.on_gpu",
        sortable: true,
      },
      {
        field: "metrics.on_cpu",
        title: "metrics.on_cpu",
        sortable: true,
      },
      {
        field: "metrics.avg",
        title: "metrics.avg",
        formatter: floatFormatter,
        sortable: true,
      },
      {
        field: "metrics.avg_process",
        title: "metrics.avg_process",
        formatter: floatFormatter,
        sortable: true,
      },
      {
        field: "metrics.dev",
        title: "metrics.dev",
        formatter: floatFormatter,
        sortable: true,
      },
      {
        field: "metrics.min",
        title: "metrics.min",
        formatter: floatFormatter,
        sortable: true,
      },
      {
        field: "metrics.max",
        title: "metrics.max",
        formatter: floatFormatter,
        sortable: true,
      },
    ],
  });
}

function getRandomColor(alpha) {
  var o = Math.round,
    r = Math.random,
    s = 255;
  return (
    "rgba(" +
    o(r() * s) +
    "," +
    o(r() * s) +
    "," +
    o(r() * s) +
    "," +
    alpha +
    ")"
  );
}

function getRandomC() {
  var o = Math.round,
    r = Math.random,
    s = 255;
  return o(r() * s);
}

$(function () {
  let tick = 0;
  let max_samples = 50;
  let sampling_time = 2000;
  let sampling_time_s = sampling_time / 1000;

  let labels = [0];
  let models = [];
  let datasets_avg = [];
  let datasets_on_gpu = [];
  let datasets_cre = [];
  let datasets_com = [];
  let model_SLAs = [];

  // set fixed colors
  let colors = ["rgba(255, 0, 0, 0.5)", "rgba(11, 212, 0, 0.5)"];
  let colorsSLA = ["rgba(133, 0, 0, 1)", "rgba(0, 133, 46, 1)"];

  for (let i = 0; i < 10; i++) {
    let r = getRandomC();
    let g = getRandomC();
    let b = getRandomC();

    colors.push("rgba(" + r + "," + g + "," + b + "," + 0.3 + ")");
    colorsSLA.push("rgba(" + r + "," + g + "," + b + "," + 1 + ")");
  }

  // get the data
  var date = new Date();
  var timestamp = (date.getTime() - sampling_time) / 1000;
  $.get(host_requests + "/metrics/model?from_ts=" + timestamp, function (data) {
    for (let i = 0; i < data.length; i++) {
      let model = data[i].model;
      models.push(model);
      let color = getRandomColor();

      datasets_avg.push({
        borderColor: colors[i],
        backgroundColor: colors[i],
        label: model,
        fill: true,
        data: [data[i].metrics_from_ts.avg],
      });
      datasets_cre.push({
        borderColor: colors[i],
        backgroundColor: colors[i],
        label: model,
        fill: true,
        data: [data[i].metrics_from_ts.created / sampling_time_s],
      });
      datasets_com.push({
        borderColor: colors[i],
        backgroundColor: colors[i],
        label: model,
        fill: true,
        data: [data[i].metrics_from_ts.completed / sampling_time_s],
      });
      datasets_on_gpu.push({
        borderColor: colors[i],
        backgroundColor: colors[i],
        label: model,
        fill: true,
        data: [data[i].metrics_from_ts.on_gpu / sampling_time_s],
      });
    }
  });

  $.get(host_containers + "/models", function (data) {
    for (let i = 0; i < data.length; i++) {
      let color = getRandomColor();
      model_SLAs[data[i].name + "_SLA"] = data[i].sla;
      datasets_avg.push({
        borderColor: colorsSLA[i],
        backgroundColor: colorsSLA[i],
        label: data[i].name + "_SLA",
        fill: false,
        data: [data[i].sla],
      });
    }
  });

  let containers = [];
  let datasets_quota = [];
  // get the data
  $.get(host_containers + "/containers", function (data) {
    colorIndex = 0;
    for (let i = 0; i < data.length; i++) {
      let model = data[i].model;
      if (model !== "all") {
        let container_id = data[i].container_id.substr(0, 12);
        containers.push(model + "_" + container_id);
        let color = getRandomColor();
        datasets_quota.push({
          borderColor: colors[colorIndex],
          backgroundColor: colors[colorIndex],
          label: model + "_" + container_id,
          fill: true,
          data: [data[i].quota / 100000],
        });
        colorIndex++;
      }
    }
  });

  let ctx_rt = document.getElementById("chart-rt").getContext("2d");
  let chart_rt = new Chart(ctx_rt, {
    type: "line",
    data: {
      labels: labels,
      datasets: datasets_avg,
    },
    options: {
      title: {
        display: true,
        text: "Response Time",
      },
      animation: false,
      scales: {
        yAxes: [
          {
            scaleLabel: {
              display: true,
              labelString: "Time [s]",
            },
            ticks: {
              beginAtZero: true,
            },
          },
        ],
      },
      elements: {
        line: {
          tension: 0,
        },
      },
    },
  });

  let ctx_cre = document.getElementById("chart-cre").getContext("2d");
  let chart_cre = new Chart(ctx_cre, {
    type: "line",
    data: {
      labels: labels,
      datasets: datasets_cre,
    },
    options: {
      title: {
        display: true,
        text: "Req. created",
      },
      animation: false,
      scales: {
        yAxes: [
          {
            scaleLabel: {
              display: true,
              labelString: "# requests",
            },
            ticks: {
              beginAtZero: true,
            },
          },
        ],
      },
      elements: {
        line: {
          tension: 0,
        },
      },
    },
  });

  let ctx_com = document.getElementById("chart-com").getContext("2d");
  let chart_com = new Chart(ctx_com, {
    type: "line",
    data: {
      labels: labels,
      datasets: datasets_com,
    },
    options: {
      title: {
        display: true,
        text: "Req. completed",
      },
      animation: false,
      scales: {
        yAxes: [
          {
            scaleLabel: {
              display: true,
              labelString: "# requests",
            },
            ticks: {
              beginAtZero: true,
            },
          },
        ],
      },
      elements: {
        line: {
          tension: 0,
        },
      },
    },
  });

  let ctx_on_gpu = document.getElementById("chart-on-gpu").getContext("2d");
  let chart_on_gpu = new Chart(ctx_on_gpu, {
    type: "line",
    data: {
      labels: labels,
      datasets: datasets_on_gpu,
    },
    options: {
      title: {
        display: true,
        text: "Requests On GPU",
      },
      animation: false,
      scales: {
        yAxes: [
          {
            scaleLabel: {
              display: true,
              labelString: "# requests",
            },
            ticks: {
              beginAtZero: true,
            },
          },
        ],
      },
      elements: {
        line: {
          tension: 0,
        },
      },
    },
  });

  let ctx_quota = document.getElementById("chart-quota").getContext("2d");
  let chart_quota = new Chart(ctx_quota, {
    type: "line",
    data: {
      labels: labels,
      datasets: datasets_quota,
    },
    options: {
      title: {
        display: true,
        text: "Core Allocations",
      },
      animation: false,
      scales: {
        yAxes: [
          {
            scaleLabel: {
              display: true,
              labelString: "Cores",
            },
            ticks: {
              beginAtZero: true,
            },
          },
        ],
      },
      elements: {
        line: {
          tension: 0,
        },
      },
    },
  });

  // update
  setInterval(function () {
    tick++;
    labels.push(tick);
    if (labels.length > max_samples) {
      labels.shift();
    }

    var date = new Date();
    var timestamp = (date.getTime() - sampling_time) / 1000;

    $.get(host_requests + "/metrics/model?from_ts=" + timestamp, function (
      data
    ) {
      let avgs = {};
      let cre = {};
      let com = {}
      let on_gpu = {};

      for (let i = 0; i < data.length; i++) {
        let model = data[i].model;
        avgs[model] = data[i].metrics_from_ts.avg;
        cre[model] = data[i].metrics_from_ts.created / sampling_time_s;
        com[model] = data[i].metrics_from_ts.completed / sampling_time_s;
        on_gpu[model] = data[i].metrics_from_ts.on_gpu / sampling_time_s;
      }

      chart_rt.data.datasets.forEach((dataset) => {
        if (dataset.label.includes("_SLA")) {
          dataset.data.push(model_SLAs[dataset.label]);
        } else {
          dataset.data.push(avgs[dataset.label]);
        }

        if (dataset.data.length > max_samples) {
          dataset.data.shift();
        }
      });

      chart_on_gpu.data.datasets.forEach((dataset) => {
        dataset.data.push(on_gpu[dataset.label]);
        if (dataset.data.length > max_samples) {
          dataset.data.shift();
        }
      });

      chart_cre.data.datasets.forEach((dataset) => {
        dataset.data.push(cre[dataset.label]);
        if (dataset.data.length > max_samples) {
          dataset.data.shift();
        }
      });

      chart_com.data.datasets.forEach((dataset) => {
        dataset.data.push(com[dataset.label]);
        if (dataset.data.length > max_samples) {
          dataset.data.shift();
        }
      });

      chart_rt.update();
      chart_on_gpu.update();
      chart_cre.update();
      chart_com.update();
    });

    $.get(host_containers + "/containers", function (data) {
      let quotas = {};

      for (let i = 0; i < data.length; i++) {
        let model = data[i].model;
        if (model !== "all") {
          let container_id = data[i].container_id.substr(0, 12);
          quotas[model + "_" + container_id] = data[i].quota / 100000;
        }
      }

      chart_quota.data.datasets.forEach((dataset) => {
        dataset.data.push(quotas[dataset.label]);
        if (dataset.data.length > max_samples) {
          dataset.data.shift();
        }
      });

      chart_quota.update();
    });
  }, sampling_time);
});
