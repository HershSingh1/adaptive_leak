within;
package TubeStudy
  "Segmented low-pressure tube for verifying the adaptive leak detector"

  model Tube
    "N-segment tube: viscous flow between segments, thermal lag, gas sources, on/off pump, leak"
    import Modelica.Constants.pi;

    // ------------------------------------------------------------------ structure (edit the file to change)
    constant Integer N = 10 "number of tube segments";

    // ------------------------------------------------------------------ geometry and gas
    parameter Real L = 5000 "tube length [m]";
    parameter Real D = 3.0 "inner diameter [m]";
    parameter Real eta = 1.8e-5 "gas dynamic viscosity [Pa s]";
    parameter Real Tref = 293.15 "reference temperature [K]";
    parameter Real Rg = 8.314 "gas constant [J/(mol K)]";
    final parameter Real Vseg = pi*D^2/4*L/N "volume of one segment [m3]";
    final parameter Real Lseg = L/N "length of one segment [m]";

    // ------------------------------------------------------------------ pump (at segment 1) and gauge
    parameter Real Spump = 40 "pump speed [m3/s] while on";
    parameter Real Plo = 97 "pump switches off at or below [Pa]";
    parameter Real Phi = 103 "pump switches on at or above [Pa]";
    parameter Integer gaugeSeg = 10 "segment holding the gauge (1..N)";

    // ------------------------------------------------------------------ gas sources, tube-average Pa/h at Tref
    parameter Real Cperm = 0.3 "seal permeation rate [Pa/h]";
    parameter Real Ep = 50000 "permeation activation energy [J/mol]";
    parameter Real q300 = 0.2 "outgassing rate at 300 h after pump-down [Pa/h]";
    parameter Real alpha = 1.0 "outgassing time exponent";
    parameter Real Ed = 45000 "outgassing activation energy [J/mol]";
    parameter Real secondFrac = 0.25 "second (slower) outgassing source as share of q300 at 300 h; 0 = off";
    parameter Real E2 = 80000 "activation energy of the second source [J/mol]";
    parameter Real agingPerMonth = 0.1 "fractional growth of permeation per 720 h; 0 = off";
    parameter Real gammaPod = 0.02 "apparent rise per pod in the tube [Pa/h]";
    parameter Real tau0 = 500 "hours since last pump-down at t = 0";
    parameter Real tVent = 1e12 "time of a vent event [s]; 1e12 = none";
    parameter Real humAmp = 0 "humidity burst after a vent [Pa/h]";

    // ------------------------------------------------------------------ thermal
    parameter Real Sgain = 5 "solar heating of the wall at full sun [K]; 0 = off";
    parameter Real tauG = 5400 "gas temperature lag behind the wall [s]";
    parameter Real shade = 0 "0..1: how much less sun the far end gets than segment 1";

    // ------------------------------------------------------------------ leak (value is tube-average Pa/h)
    parameter Real leakType = 0 "0 none, 1 sudden (1 h ramp), 2 ramp, 3 creep, 4 intermittent";
    parameter Real leakSize = 0.1 "final leak rate, tube-average [Pa/h]";
    parameter Real leakT0 = 1.5e6 "leak start [s]";
    parameter Integer leakSeg = 5 "segment holding the leak (1..N)";
    parameter Real rampH = 24 "ramp duration for type 2 [h]";
    parameter Real creepDays = 21 "growth duration for type 3 [days]";
    parameter Real onH = 24 "on-time for type 4 [h]";
    parameter Real offH = 24 "off-time for type 4 [h]";

    // ------------------------------------------------------------------ weather and traffic drivers (file: drivers.txt)
    // columns: 1 time [s], 2 ambient/effective temperature [K], 3 solar 0..1, 4 wind/rain wall dip [K], 5 pods
    Modelica.Blocks.Sources.CombiTimeTable drv(
      tableOnFile = true,
      tableName = "drivers",
      fileName = "drivers.txt",
      columns = {2, 3, 4, 5},
      smoothness = Modelica.Blocks.Types.Smoothness.LinearSegments,
      extrapolation = Modelica.Blocks.Types.Extrapolation.HoldLastPoint);

    // ------------------------------------------------------------------ states
    Real P[N](each start = 97.5, each fixed = true) "segment pressures [Pa]";
    Real Tg[N](each start = 293.15) "segment gas temperatures [K]";

    // ------------------------------------------------------------------ algebraic variables
    Real Twall[N] "wall temperature [K]";
    Real dT[N] "gas temperature rate [K/s]";
    Real perm[N], out1[N], out2[N], hum[N], pod[N], src[N] "sources [Pa/h]";
    Real expo[N] "share of solar reaching each segment";
    Real cond[N-1] "viscous conductance between segments i and i+1 [m3/s]";
    Real Q[N-1] "throughput from segment i to i+1 [Pa m3/s]";
    Real Qin[N], Qout[N], Qpump[N] "[Pa m3/s]";
    Real tau "hours since pump-down";
    Real leakVal "leak, tube-average [Pa/h]";
    Real tleak "hours since leak start";

    // ------------------------------------------------------------------ pump controller
    discrete Boolean pumpOn(start = false, fixed = true);
    discrete Integer nPumps(start = 0, fixed = true);
    Real Pg "pressure at the gauge segment [Pa]";

    // ------------------------------------------------------------------ outputs for the adapter (names are fixed)
    Real pumpOnReal "1 while the pump runs";
    Real nPumpsReal "count of pump starts";
    Real Tsensor "wall temperature as the sensor sees it (30 % of the rain dip) [K]";
    Real Tamb "ambient temperature [K]";
    Real podsOut "pods in the tube";
    Real leakTotal "true leak [Pa/h]  (diagnostic only, never given to the detector)";
    Real Tgas "gas temperature at the gauge segment [K]";

  initial equation
    for i in 1:N loop
      Tg[i] = Twall[i];
    end for;

  equation
    // ---- time since pump-down, vent, leak shape
    tau = if time >= tVent then 24 + (time - tVent)/3600 else tau0 + time/3600;
    tleak = (time - leakT0)/3600;
    leakVal = if time < leakT0 or leakType < 0.5 then 0
              elseif leakType < 1.5 then leakSize*min(max(tleak/1, 0), 1)
              elseif leakType < 2.5 then leakSize*min(max(tleak/rampH, 0), 1)
              elseif leakType < 3.5 then leakSize*min(max(tleak/(creepDays*24), 0), 1)
              else leakSize*min(max(tleak/1, 0), 1)*(if mod(tleak, onH + offH) < onH then 1 else 0);

    // ---- thermal and sources per segment
    for i in 1:N loop
      expo[i] = 1 - shade*(i - 1)/(N - 1);
      Twall[i] = drv.y[1] + expo[i]*Sgain*drv.y[2] - drv.y[3];
      dT[i] = (Twall[i] - Tg[i])/tauG;
      der(Tg[i]) = dT[i];
      perm[i] = Cperm*(1 + agingPerMonth*time/(720*3600))*exp(-Ep/Rg*(1/Tg[i] - 1/Tref));
      out1[i] = q300*(tau/300)^(-alpha)*exp(-Ed/Rg*(1/Tg[i] - 1/Tref));
      out2[i] = secondFrac*q300*sqrt(300/tau)*exp(-E2/Rg*(1/Tg[i] - 1/Tref));
      hum[i] = if time >= tVent then humAmp*exp(-(time - tVent)/(60*3600)) else 0;
      pod[i] = gammaPod*drv.y[4];
      src[i] = perm[i] + out1[i] + out2[i] + hum[i] + pod[i]
               + (if i == leakSeg then leakVal*N else 0);
    end for;

    // ---- viscous (Poiseuille) flow between neighbouring segments: C = pi d^4 Pbar / (256 eta Lseg)
    for i in 1:N-1 loop
      cond[i] = pi*D^4/(256*eta*Lseg)*(P[i] + P[i + 1])/2;
      Q[i] = cond[i]*(P[i] - P[i + 1]);
    end for;
    Qin[1] = 0;
    for i in 2:N loop
      Qin[i] = Q[i - 1];
    end for;
    for i in 1:N-1 loop
      Qout[i] = Q[i];
    end for;
    Qout[N] = 0;
    Qpump[1] = if pumpOn then Spump*P[1] else 0;
    for i in 2:N loop
      Qpump[i] = 0;
    end for;

    // ---- pressure balance of each segment: gas law + sources + flow - pump
    for i in 1:N loop
      der(P[i]) = P[i]/Tg[i]*dT[i] + src[i]/3600 + (Qin[i] - Qout[i] - Qpump[i])/Vseg;
    end for;

    // ---- on/off pump with deadband, driven by the gauge segment
    Pg = P[gaugeSeg];
    when Pg >= Phi then
      pumpOn = true;
      nPumps = pre(nPumps) + 1;
    elsewhen Pg <= Plo then
      pumpOn = false;
      nPumps = pre(nPumps);
    end when;

    // ---- outputs
    pumpOnReal = if pumpOn then 1 else 0;
    nPumpsReal = nPumps;
    Tsensor = drv.y[1] + expo[gaugeSeg]*Sgain*drv.y[2] - 0.3*drv.y[3];
    Tamb = drv.y[1];
    podsOut = drv.y[4];
    leakTotal = leakVal;
    Tgas = Tg[gaugeSeg];

    annotation(experiment(StartTime = 0, StopTime = 5184000, Interval = 600, Tolerance = 1e-7));
  end Tube;

end TubeStudy;
