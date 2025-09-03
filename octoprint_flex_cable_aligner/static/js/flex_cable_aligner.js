(function() {
  function FCAViewModel(parameters) {
    var self = this;

    self.settings = parameters[0];

    self.carriage = ko.observable("-");
    self.feed = ko.observable(0);
    self.dir = ko.observable([0,0,0]);
    self.operational = ko.observable(false);

    self.feedText = ko.pureComputed(function(){
      return Math.round(self.feed());
    });
    self.carriageLabel = ko.pureComputed(function(){
      var c = self.carriage();
      if (c === 1 || c === "1") return "1 (XYZ)";
      if (c === 2 || c === "2") return "2 (ABC)";
      return c;
    });
    self.dirText = ko.pureComputed(function(){
      var d = self.dir() || [0,0,0];
      return "[" + d.join(", ") + "]";
    });

    function poll(){
      $.ajax({
        url: API_BASEURL + "plugin/flex_cable_aligner",
        type: "GET",
        dataType: "json"
      }).done(function(data){
        if (data) {
          self.carriage(data.carriage);
          self.feed(data.feed || 0);
          self.dir(data.dir || [0,0,0]);
          self.operational(!!data.operational);
        }
      }).always(function(){
        window.setTimeout(poll, 500);
      });
    }

    self.onStartup = function(){
      poll();
    };
  }

  OCTOPRINT_VIEWMODELS.push({
    construct: FCAViewModel,
    dependencies: ["settingsViewModel"],
    elements: ["#fca-panel"]
  });
})();
