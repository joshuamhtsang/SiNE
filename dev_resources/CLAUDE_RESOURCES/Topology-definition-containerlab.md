[ Skip to content ](https://containerlab.dev/manual/topo-def-file/#topology-definition)

[ ](https://containerlab.dev/ "containerlab")

containerlab 

Topology definition 

Type to start searching




[ srl-labs/containerlab 

  * v0.72.0
  * 2.3k
  * 382

](https://github.com/srl-labs/containerlab "Go to repository")

  * [ Home ](https://containerlab.dev/)
  * [ Installation ](https://containerlab.dev/install/)
  * [ Quick start ](https://containerlab.dev/quickstart/)
  * [ Kinds ](https://containerlab.dev/manual/kinds/)
  * [ User manual ](https://containerlab.dev/manual/topo-def-file/)
  * [ Command reference ](https://containerlab.dev/cmd/deploy/)
  * [ Lab examples ](https://containerlab.dev/lab-examples/lab-examples/)
  * [ Release notes ](https://containerlab.dev/rn/0.72/)
  * [ Community ](https://containerlab.dev/community/)



[ ](https://containerlab.dev/ "containerlab") containerlab 

[ srl-labs/containerlab 

  * v0.72.0
  * 2.3k
  * 382

](https://github.com/srl-labs/containerlab "Go to repository")

  * [ Home  ](https://containerlab.dev/)
  * [ Installation  ](https://containerlab.dev/install/)
  * [ Quick start  ](https://containerlab.dev/quickstart/)
  * [ Kinds  ](https://containerlab.dev/manual/kinds/)
  * User manual  User manual 
    * Topology definition  [ Topology definition  ](https://containerlab.dev/manual/topo-def-file/) Table of contents 
      * [ Topology definition components  ](https://containerlab.dev/manual/topo-def-file/#topology-definition-components)
        * [ Name  ](https://containerlab.dev/manual/topo-def-file/#name)
        * [ Prefix  ](https://containerlab.dev/manual/topo-def-file/#prefix)
        * [ Topology  ](https://containerlab.dev/manual/topo-def-file/#topology)
          * [ Nodes  ](https://containerlab.dev/manual/topo-def-file/#nodes)
          * [ Links  ](https://containerlab.dev/manual/topo-def-file/#links)
            * [ Interface naming  ](https://containerlab.dev/manual/topo-def-file/#interface-naming)
              * [ Aliases  ](https://containerlab.dev/manual/topo-def-file/#aliases)
            * [ Brief format  ](https://containerlab.dev/manual/topo-def-file/#brief-format)
            * [ Extended format  ](https://containerlab.dev/manual/topo-def-file/#extended-format)
              * [ veth  ](https://containerlab.dev/manual/topo-def-file/#veth)
              * [ mgmt-net  ](https://containerlab.dev/manual/topo-def-file/#mgmt-net)
              * [ macvlan  ](https://containerlab.dev/manual/topo-def-file/#macvlan)
              * [ host  ](https://containerlab.dev/manual/topo-def-file/#host)
              * [ vxlan  ](https://containerlab.dev/manual/topo-def-file/#vxlan)
              * [ vxlan-stitched  ](https://containerlab.dev/manual/topo-def-file/#vxlan-stitched)
              * [ dummy  ](https://containerlab.dev/manual/topo-def-file/#dummy)
            * [ Variables  ](https://containerlab.dev/manual/topo-def-file/#variables)
            * [ IP Addresses  ](https://containerlab.dev/manual/topo-def-file/#ip-addresses)
          * [ Groups  ](https://containerlab.dev/manual/topo-def-file/#groups)
          * [ Kinds  ](https://containerlab.dev/manual/topo-def-file/#kinds)
          * [ Defaults  ](https://containerlab.dev/manual/topo-def-file/#defaults)
        * [ Settings  ](https://containerlab.dev/manual/topo-def-file/#settings)
          * [ Certificate authority  ](https://containerlab.dev/manual/topo-def-file/#certificate-authority)
      * [ Environment variables  ](https://containerlab.dev/manual/topo-def-file/#environment-variables)
      * [ Magic Variables  ](https://containerlab.dev/manual/topo-def-file/#magic-variables)
      * [ Generated topologies  ](https://containerlab.dev/manual/topo-def-file/#generated-topologies)
    * [ Nodes  ](https://containerlab.dev/manual/nodes/)
    * [ Kinds  ](https://containerlab.dev/manual/kinds/)

Kinds 
      * Nokia  Nokia 
        * [ Nokia SR Linux  ](https://containerlab.dev/manual/kinds/srl/)
        * [ Nokia SR OS (SR-SIM)  ](https://containerlab.dev/manual/kinds/sros/)
        * [ Nokia SR OS (vSIM)  ](https://containerlab.dev/manual/kinds/vr-sros/)
      * Arista  Arista 
        * [ Arista cEOS  ](https://containerlab.dev/manual/kinds/ceos/)
        * [ Arista vEOS  ](https://containerlab.dev/manual/kinds/vr-veos/)
      * Cisco  Cisco 
        * [ Cisco XRd  ](https://containerlab.dev/manual/kinds/xrd/)
        * [ Cisco XRv9k  ](https://containerlab.dev/manual/kinds/vr-xrv9k/)
        * [ Cisco XRv  ](https://containerlab.dev/manual/kinds/vr-xrv/)
        * [ Cisco CSR1000v  ](https://containerlab.dev/manual/kinds/vr-csr/)
        * [ Cisco Nexus 9000v  ](https://containerlab.dev/manual/kinds/vr-n9kv/)
        * [ Cisco 8000  ](https://containerlab.dev/manual/kinds/c8000/)
        * [ Cisco c8000v  ](https://containerlab.dev/manual/kinds/vr-c8000v/)
        * [ Cisco SD-WAN  ](https://containerlab.dev/manual/kinds/cisco_sdwan/)
        * [ Cisco Catalyst 9000v  ](https://containerlab.dev/manual/kinds/vr-cat9kv/)
        * [ Cisco IOL  ](https://containerlab.dev/manual/kinds/cisco_iol/)
        * [ Cisco ASAv  ](https://containerlab.dev/manual/kinds/cisco_asav/)
        * [ Cisco FTDv  ](https://containerlab.dev/manual/kinds/vr-ftdv/)
      * Juniper  Juniper 
        * [ Juniper cRPD  ](https://containerlab.dev/manual/kinds/crpd/)
        * [ Juniper vMX  ](https://containerlab.dev/manual/kinds/vr-vmx/)
        * [ Juniper vQFX  ](https://containerlab.dev/manual/kinds/vr-vqfx/)
        * [ Juniper vSRX  ](https://containerlab.dev/manual/kinds/vr-vsrx/)
        * [ Juniper vJunos-router  ](https://containerlab.dev/manual/kinds/vr-vjunosrouter/)
        * [ Juniper vJunos-switch  ](https://containerlab.dev/manual/kinds/vr-vjunosswitch/)
        * [ Juniper vJunosEvolved  ](https://containerlab.dev/manual/kinds/vr-vjunosevolved/)
        * [ Juniper cJunosEvolved  ](https://containerlab.dev/manual/kinds/cjunosevolved/)
      * [ Cumulus VX  ](https://containerlab.dev/manual/kinds/cvx/)
      * [ Aruba AOS-CX  ](https://containerlab.dev/manual/kinds/vr-aoscx/)
      * SONiC  SONiC 
        * [ Container  ](https://containerlab.dev/manual/kinds/sonic-vs/)
        * [ VM  ](https://containerlab.dev/manual/kinds/sonic-vm/)
      * Dell  Dell 
        * [ FTOS10v  ](https://containerlab.dev/manual/kinds/vr-ftosv/)
        * [ Enterprise SONiC  ](https://containerlab.dev/manual/kinds/dell_sonic/)
      * [ MikroTik RouterOS  ](https://containerlab.dev/manual/kinds/vr-ros/)
      * [ Huawei VRP  ](https://containerlab.dev/manual/kinds/huawei_vrp/)
      * [ IPInfusion OcNOS  ](https://containerlab.dev/manual/kinds/ipinfusion-ocnos/)
      * [ VyOS Networks VyOS  ](https://containerlab.dev/manual/kinds/vyosnetworks_vyos/)
      * [ OpenBSD  ](https://containerlab.dev/manual/kinds/openbsd/)
      * [ FreeBSD  ](https://containerlab.dev/manual/kinds/freebsd/)
      * [ OpenWRT  ](https://containerlab.dev/manual/kinds/openwrt/)
      * [ Keysight IXIA-C One  ](https://containerlab.dev/manual/kinds/keysight_ixia-c-one/)
      * [ Ostinato  ](https://containerlab.dev/manual/kinds/ostinato/)
      * [ Check Point Cloudguard  ](https://containerlab.dev/manual/kinds/checkpoint_cloudguard/)
      * [ Fortinet Fortigate  ](https://containerlab.dev/manual/kinds/fortinet_fortigate/)
      * [ Palo Alto PAN  ](https://containerlab.dev/manual/kinds/vr-pan/)
      * [ 6WIND VSR  ](https://containerlab.dev/manual/kinds/6wind_vsr/)
      * [ Arrcus ArcOS  ](https://containerlab.dev/manual/kinds/arrcus_arcos/)
      * [ FD.io VPP  ](https://containerlab.dev/manual/kinds/fdio_vpp/)
      * [ KinD  ](https://containerlab.dev/manual/kinds/k8s-kind/)
      * [ Linux bridge  ](https://containerlab.dev/manual/kinds/bridge/)
      * [ Linux container  ](https://containerlab.dev/manual/kinds/linux/)
      * [ Generic VM  ](https://containerlab.dev/manual/kinds/generic_vm/)
      * [ RARE/freeRtr  ](https://containerlab.dev/manual/kinds/rare-freertr/)
      * [ Openvswitch bridge  ](https://containerlab.dev/manual/kinds/ovs-bridge/)
      * [ External container  ](https://containerlab.dev/manual/kinds/ext-container/)
      * [ Host  ](https://containerlab.dev/manual/kinds/host/)
    * [ Configuration artifacts  ](https://containerlab.dev/manual/conf-artifacts/)
    * [ Network  ](https://containerlab.dev/manual/network/)
    * [ Packet capture & Wireshark  ](https://containerlab.dev/manual/wireshark/)
    * [ VM based routers integration  ](https://containerlab.dev/manual/vrnetlab/)
    * [ Clabernetes  ](https://containerlab.dev/manual/clabernetes/)

Clabernetes 
      * [ Install  ](https://containerlab.dev/manual/clabernetes/install/)
      * [ Quickstart  ](https://containerlab.dev/manual/clabernetes/quickstart/)
      * [ Packet capture in c9s  ](https://containerlab.dev/manual/clabernetes/pcap/)
    * [ Node filtering  ](https://containerlab.dev/manual/node-filtering/)
    * [ Multi-node labs  ](https://containerlab.dev/manual/multi-node/)
    * [ Certificate management  ](https://containerlab.dev/manual/cert/)
    * [ Inventory  ](https://containerlab.dev/manual/inventory/)
    * [ Image management  ](https://containerlab.dev/manual/images/)
    * [ Labs and Codespaces  ](https://containerlab.dev/manual/codespaces/)
    * [ VS Code Extension  ](https://containerlab.dev/manual/vsc-extension/)
    * [ Link Impairments  ](https://containerlab.dev/manual/impairments/)
    * [ Share lab access  ](https://containerlab.dev/manual/share-access/)
    * [ Configuration management  ](https://containerlab.dev/manual/config-mgmt/)
    * [ Developers guide  ](https://containerlab.dev/manual/dev/)

Developers guide 
      * [ Documentation  ](https://containerlab.dev/manual/dev/doc/)
      * [ Testing  ](https://containerlab.dev/manual/dev/test/)
      * [ Debugging  ](https://containerlab.dev/manual/dev/debug/)
  * Command reference  Command reference 
    * [ deploy  ](https://containerlab.dev/cmd/deploy/)
    * [ destroy  ](https://containerlab.dev/cmd/destroy/)
    * [ redeploy  ](https://containerlab.dev/cmd/redeploy/)
    * [ inspect  ](https://containerlab.dev/cmd/inspect/)

inspect 
      * [ interfaces  ](https://containerlab.dev/cmd/inspect/interfaces/)
    * [ events  ](https://containerlab.dev/cmd/events/)
    * [ save  ](https://containerlab.dev/cmd/save/)
    * [ exec  ](https://containerlab.dev/cmd/exec/)
    * [ generate  ](https://containerlab.dev/cmd/generate/)
    * [ graph  ](https://containerlab.dev/cmd/graph/)
    * tools  tools 
      * [ disable-tx-offload  ](https://containerlab.dev/cmd/tools/disable-tx-offload/)
      * veth  veth 
        * [ create  ](https://containerlab.dev/cmd/tools/veth/create/)
      * vxlan  vxlan 
        * [ create  ](https://containerlab.dev/cmd/tools/vxlan/create/)
        * [ delete  ](https://containerlab.dev/cmd/tools/vxlan/delete/)
      * cert  cert 
        * ca  ca 
          * [ create  ](https://containerlab.dev/cmd/tools/cert/ca/create/)
        * [ sign  ](https://containerlab.dev/cmd/tools/cert/sign/)
      * netem  netem 
        * [ set  ](https://containerlab.dev/cmd/tools/netem/set/)
        * [ reset  ](https://containerlab.dev/cmd/tools/netem/reset/)
        * [ show  ](https://containerlab.dev/cmd/tools/netem/show/)
      * api-server  api-server 
        * [ start  ](https://containerlab.dev/cmd/tools/api-server/start/)
        * [ stop  ](https://containerlab.dev/cmd/tools/api-server/stop/)
        * [ status  ](https://containerlab.dev/cmd/tools/api-server/status/)
      * sshx  sshx 
        * [ attach  ](https://containerlab.dev/cmd/tools/sshx/attach/)
        * [ detach  ](https://containerlab.dev/cmd/tools/sshx/detach/)
        * [ reattach  ](https://containerlab.dev/cmd/tools/sshx/reattach/)
        * [ list  ](https://containerlab.dev/cmd/tools/sshx/list/)
      * gotty  gotty 
        * [ attach  ](https://containerlab.dev/cmd/tools/gotty/attach/)
        * [ detach  ](https://containerlab.dev/cmd/tools/gotty/detach/)
        * [ reattach  ](https://containerlab.dev/cmd/tools/gotty/reattach/)
        * [ list  ](https://containerlab.dev/cmd/tools/gotty/list/)
      * [ snapshot save  ](https://containerlab.dev/cmd/tools/snapshot/save/)
    * [ version  ](https://containerlab.dev/cmd/version/)

version 
      * [ check  ](https://containerlab.dev/cmd/version/check/)
    * [ completions  ](https://containerlab.dev/cmd/completion/)
  * Lab examples  Lab examples 
    * [ About  ](https://containerlab.dev/lab-examples/lab-examples/)
    * [ Single SR Linux node  ](https://containerlab.dev/lab-examples/single-srl/)
    * [ Two SR Linux nodes  ](https://containerlab.dev/lab-examples/two-srls/)
    * [ 3-nodes Clos fabric  ](https://containerlab.dev/lab-examples/min-clos/)
    * [ 5-stage Clos fabric  ](https://containerlab.dev/lab-examples/min-5clos/)
    * [ Nokia SR Linux and Arista cEOS  ](https://containerlab.dev/lab-examples/srl-ceos/)
    * [ Nokia SR Linux and Juniper cRPD  ](https://containerlab.dev/lab-examples/srl-crpd/)
    * [ Nokia SR Linux and SONiC  ](https://containerlab.dev/lab-examples/srl-sonic/)
    * [ External bridge capability  ](https://containerlab.dev/lab-examples/ext-bridge/)
    * [ WAN topology  ](https://containerlab.dev/lab-examples/wan/)
    * [ Peering lab  ](https://containerlab.dev/lab-examples/peering-lab/)
    * [ Nokia SR Linux and Nokia SR OS  ](https://containerlab.dev/lab-examples/sr-sim/)
    * [ Nokia SR Linux and Juniper vMX  ](https://containerlab.dev/lab-examples/vr-vmx/)
    * [ Nokia SR Linux and Cisco XRd  ](https://containerlab.dev/lab-examples/srl-xrd/)
    * [ Nokia SR Linux and Cisco XRv9k  ](https://containerlab.dev/lab-examples/vr-xrv9k/)
    * [ Nokia SR Linux and Cisco XRv  ](https://containerlab.dev/lab-examples/vr-xrv/)
    * [ Nokia SR Linux and FRR  ](https://containerlab.dev/lab-examples/srl-frr/)
    * [ Nokia SR Linux and Juniper vJunos-switch  ](https://containerlab.dev/lab-examples/srl-vjunos-switch/)
    * [ Nokia SR Linux and Juniper vJunosEvolved  ](https://containerlab.dev/lab-examples/srl-vjunosevolved/)
    * [ Nokia SR Linux and Juniper cJunosEvolved  ](https://containerlab.dev/lab-examples/srl-cjunosevolved/)
    * [ Nokia SR Linux and Arrcus ArcOS  ](https://containerlab.dev/lab-examples/srl-arcos/)
    * [ FRR  ](https://containerlab.dev/lab-examples/frr01/)
    * [ Cumulus Linux and FRR  ](https://containerlab.dev/lab-examples/cvx01/)
    * [ Cumulus Linux (docker runtime) and Host  ](https://containerlab.dev/lab-examples/cvx02/)
    * [ BGP VPLS between Nokia and Juniper  ](https://containerlab.dev/lab-examples/bgp-vpls-nok-jun/)
    * [ Keysight IXIA-C and Nokia SR Linux  ](https://containerlab.dev/lab-examples/ixiacone-srl/)
    * [ Ostinato and Nokia SR Linux  ](https://containerlab.dev/lab-examples/ost-srl/)
    * [ Multi-node labs  ](https://containerlab.dev/lab-examples/multinode/)
    * [ RARE/freeRtr  ](https://containerlab.dev/lab-examples/rare-freertr/)
    * [ Juniper vSRX  ](https://containerlab.dev/lab-examples/vsrx01/)
    * [ OpenBSD  ](https://containerlab.dev/lab-examples/openbsd01/)
    * [ Cisco ASAv  ](https://containerlab.dev/lab-examples/asav01/)
    * [ Cisco FTDv  ](https://containerlab.dev/lab-examples/ftdv01/)
    * Templated labs  Templated labs 
      * [ Leaf-spine topology  ](https://containerlab.dev/lab-examples/templated01/)
      * [ 5-stage Clos topology  ](https://containerlab.dev/lab-examples/templated02/)
    * [ Generic VM  ](https://containerlab.dev/lab-examples/generic_vm01/)
  * Release notes  Release notes 
    * [ 0.72  ](https://containerlab.dev/rn/0.72/)
    * [ 0.71  ](https://containerlab.dev/rn/0.71/)
    * [ 0.70  ](https://containerlab.dev/rn/0.70/)
    * [ 0.69  ](https://containerlab.dev/rn/0.69/)
    * [ 0.68  ](https://containerlab.dev/rn/0.68/)
    * [ 0.67  ](https://containerlab.dev/rn/0.67/)
    * [ 0.66  ](https://containerlab.dev/rn/0.66/)
    * [ 0.65  ](https://containerlab.dev/rn/0.65/)
    * [ 0.64  ](https://containerlab.dev/rn/0.64/)
    * [ 0.63  ](https://containerlab.dev/rn/0.63/)
    * [ 0.62  ](https://containerlab.dev/rn/0.62/)
    * [ 0.61  ](https://containerlab.dev/rn/0.61/)
    * [ 0.60  ](https://containerlab.dev/rn/0.60/)
    * [ 0.59  ](https://containerlab.dev/rn/0.59/)
    * [ 0.58  ](https://containerlab.dev/rn/0.58/)
    * [ 0.57  ](https://containerlab.dev/rn/0.57/)
    * [ 0.56  ](https://containerlab.dev/rn/0.56/)
    * [ 0.55  ](https://containerlab.dev/rn/0.55/)
    * [ 0.54  ](https://containerlab.dev/rn/0.54/)
    * [ 0.53  ](https://containerlab.dev/rn/0.53/)
    * [ 0.52  ](https://containerlab.dev/rn/0.52/)
    * [ 0.51  ](https://containerlab.dev/rn/0.51/)
    * [ 0.50  ](https://containerlab.dev/rn/0.50/)
    * [ 0.49  ](https://containerlab.dev/rn/0.49/)
    * [ 0.48  ](https://containerlab.dev/rn/0.48/)
    * [ 0.47  ](https://containerlab.dev/rn/0.47/)
    * [ 0.46  ](https://containerlab.dev/rn/0.46/)
    * [ 0.45  ](https://containerlab.dev/rn/0.45/)
    * [ 0.44  ](https://containerlab.dev/rn/0.44/)
    * [ 0.43  ](https://containerlab.dev/rn/0.43/)
    * [ 0.42  ](https://containerlab.dev/rn/0.42/)
    * [ 0.41  ](https://containerlab.dev/rn/0.41/)
    * [ 0.40  ](https://containerlab.dev/rn/0.40/)
    * [ 0.39  ](https://containerlab.dev/rn/0.39/)
    * [ 0.38  ](https://containerlab.dev/rn/0.38/)
    * [ 0.37  ](https://containerlab.dev/rn/0.37/)
    * [ 0.36  ](https://containerlab.dev/rn/0.36/)
    * [ 0.35  ](https://containerlab.dev/rn/0.35/)
    * [ 0.34  ](https://containerlab.dev/rn/0.34/)
    * [ 0.33  ](https://containerlab.dev/rn/0.33/)
    * [ 0.32  ](https://containerlab.dev/rn/0.32/)
    * [ 0.31  ](https://containerlab.dev/rn/0.31/)
    * [ 0.30  ](https://containerlab.dev/rn/0.30/)
    * [ 0.29  ](https://containerlab.dev/rn/0.29/)
    * [ 0.28  ](https://containerlab.dev/rn/0.28/)
    * [ 0.27  ](https://containerlab.dev/rn/0.27/)
    * [ 0.26  ](https://containerlab.dev/rn/0.26/)
    * [ 0.25  ](https://containerlab.dev/rn/0.25/)
    * [ 0.24  ](https://containerlab.dev/rn/0.24/)
    * [ 0.23  ](https://containerlab.dev/rn/0.23/)
    * [ 0.22  ](https://containerlab.dev/rn/0.22/)
    * [ 0.21  ](https://containerlab.dev/rn/0.21/)
    * [ 0.20  ](https://containerlab.dev/rn/0.20/)
    * [ 0.19  ](https://containerlab.dev/rn/0.19/)
    * [ 0.18  ](https://containerlab.dev/rn/0.18/)
    * [ 0.17  ](https://containerlab.dev/rn/0.17/)
    * [ 0.16  ](https://containerlab.dev/rn/0.16/)
    * [ 0.15  ](https://containerlab.dev/rn/0.15/)
    * [ 0.14.4  ](https://containerlab.dev/rn/0.14.4/)
    * [ 0.14.3  ](https://containerlab.dev/rn/0.14.3/)
    * [ 0.14.2  ](https://containerlab.dev/rn/0.14.2/)
    * [ 0.14.1  ](https://containerlab.dev/rn/0.14.1/)
    * [ 0.14.0  ](https://containerlab.dev/rn/0.14.0/)
    * [ 0.13.0  ](https://containerlab.dev/rn/0.13.0/)
    * [ 0.12.0  ](https://containerlab.dev/rn/0.12.0/)
    * [ 0.11.0  ](https://containerlab.dev/rn/0.11.0/)
  * [ Community  ](https://containerlab.dev/community/)



Table of contents 

  * [ Topology definition components  ](https://containerlab.dev/manual/topo-def-file/#topology-definition-components)
    * [ Name  ](https://containerlab.dev/manual/topo-def-file/#name)
    * [ Prefix  ](https://containerlab.dev/manual/topo-def-file/#prefix)
    * [ Topology  ](https://containerlab.dev/manual/topo-def-file/#topology)
      * [ Nodes  ](https://containerlab.dev/manual/topo-def-file/#nodes)
      * [ Links  ](https://containerlab.dev/manual/topo-def-file/#links)
        * [ Interface naming  ](https://containerlab.dev/manual/topo-def-file/#interface-naming)
          * [ Aliases  ](https://containerlab.dev/manual/topo-def-file/#aliases)
        * [ Brief format  ](https://containerlab.dev/manual/topo-def-file/#brief-format)
        * [ Extended format  ](https://containerlab.dev/manual/topo-def-file/#extended-format)
          * [ veth  ](https://containerlab.dev/manual/topo-def-file/#veth)
          * [ mgmt-net  ](https://containerlab.dev/manual/topo-def-file/#mgmt-net)
          * [ macvlan  ](https://containerlab.dev/manual/topo-def-file/#macvlan)
          * [ host  ](https://containerlab.dev/manual/topo-def-file/#host)
          * [ vxlan  ](https://containerlab.dev/manual/topo-def-file/#vxlan)
          * [ vxlan-stitched  ](https://containerlab.dev/manual/topo-def-file/#vxlan-stitched)
          * [ dummy  ](https://containerlab.dev/manual/topo-def-file/#dummy)
        * [ Variables  ](https://containerlab.dev/manual/topo-def-file/#variables)
        * [ IP Addresses  ](https://containerlab.dev/manual/topo-def-file/#ip-addresses)
      * [ Groups  ](https://containerlab.dev/manual/topo-def-file/#groups)
      * [ Kinds  ](https://containerlab.dev/manual/topo-def-file/#kinds)
      * [ Defaults  ](https://containerlab.dev/manual/topo-def-file/#defaults)
    * [ Settings  ](https://containerlab.dev/manual/topo-def-file/#settings)
      * [ Certificate authority  ](https://containerlab.dev/manual/topo-def-file/#certificate-authority)
  * [ Environment variables  ](https://containerlab.dev/manual/topo-def-file/#environment-variables)
  * [ Magic Variables  ](https://containerlab.dev/manual/topo-def-file/#magic-variables)
  * [ Generated topologies  ](https://containerlab.dev/manual/topo-def-file/#generated-topologies)



[ ](https://github.com/srl-labs/containerlab/edit/main/docs/manual/topo-def-file.md "Edit this page")

# Topology definition[#](https://containerlab.dev/manual/topo-def-file/#topology-definition "Permanent link")

Containerlab builds labs based on the topology information that users pass to it. This topology information is expressed as a code contained in the _topology definition file_ which structure is the prime focus of this document.

YAML

YAML

## Topology definition components[#](https://containerlab.dev/manual/topo-def-file/#topology-definition-components "Permanent link")

The topology definition file is a configuration file expressed in YAML and has a name pattern of `*.clab.yml`[1](https://containerlab.dev/manual/topo-def-file/#fn:1). In this document, we take a pre-packaged [Nokia SR Linux and Arista cEOS](https://containerlab.dev/lab-examples/srl-ceos/) lab and explain the topology definition structure using its definition file [srlceos01.clab.yml](https://github.com/srl-labs/containerlab/tree/main/lab-examples/srlceos01/srlceos01.clab.yml) which is pasted below:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-1)name: srlceos01
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-2)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-3)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-4)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-5)    srl:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-6)      kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-7)      image: ghcr.io/nokia/srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-8)    ceos:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-9)      kind: arista_ceos
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-10)      image: ceos:4.32.0F
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-11)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-12)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-0-13)    - endpoints: ["srl:e1-1", "ceos:eth1"]
    

Note

Containerlab provides a [JSON schema file](https://github.com/srl-labs/containerlab/blob/main/schemas/clab.schema.json) for the topology file. The schema is used to live-validate user's input if a code editor supports this feature.

This topology results in the two nodes being started up and interconnected with each other using a single point-to-point interface:

Lab host

SR Linux

mgmt

  


vethXXX

netns: default

netns: container1

docker network: clab  


Lab wiring diagram

br-XXX

Pool  


IPv4: 172.20.20.0/24  
IPv6: 2001:172:20:20::/80

172.20.20.1

2001:172:20:20::1

srl

Lab logical diagram

Arista cEOS

mgmt

vethXXX

netns: container2

e1-1

eth1

ceos

e1-1

eth1

docker network:  
clab

Let's touch on the key components of the topology definition file used in this example.

### Name[#](https://containerlab.dev/manual/topo-def-file/#name "Permanent link")

The topology must have a name associated with it. The name is used to distinct one topology from another, to allow multiple topologies to be deployed on the same host without clashes.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-1-1)name: srlceos01
    

Its user's responsibility to give labs unique names if they plan to run multiple labs.

The name is a free-formed string, though it is better not to use dashes (`-`) as they are used to separate lab names from node names.

When containerlab starts the containers, their names will be generated using the following pattern: `clab-${lab-name}-${node-name}`. The lab name here is used to make the container's names unique between two different labs, even if the nodes are named the same.

### Prefix[#](https://containerlab.dev/manual/topo-def-file/#prefix "Permanent link")

It is possible to change the prefix that containerlab adds to node names. The `prefix` parameter is in charge of that. It follows the below-mentioned logic:

  1. When `prefix` is not present in the topology file, the default prefix logic applies. Containers will be named as `clab-<lab-name>-<node-name>`.
  2. When `prefix` is set to some value, for example, `myprefix`, this string is used instead of `clab`, and the resulting container name will be: `myprefix-<lab-name>-<node-name>`.
  3. When `prefix` is set to a magic value `__lab-name` the resulting container name will not have the `clab` prefix, but will keep the lab name: `<lab-name>-<node-name>`.
  4. When set to an empty string, the node names will not be prefixed at all. If your node is named `mynode`, you will get the `mynode` container in your system.



Warning

In the case of an empty prefix, you have to keep in mind that nodes need to be named uniquely across all labs.

Examples:

[custom prefix](https://containerlab.dev/manual/topo-def-file/#__tabbed_1_1)[empty prefix](https://containerlab.dev/manual/topo-def-file/#__tabbed_1_2)
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-2-1)name: mylab
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-2-2)prefix: myprefix
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-2-3)nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-2-4)  n1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-2-5)  # <some config>
    

With a prefix set to `myprefix` the container name for node `n1` will be `myprefix-mylab-n1`.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-3-1)name: mylab
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-3-2)prefix: ""
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-3-3)nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-3-4)  n1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-3-5)  # <some config>
    

When a prefix is set to an empty string, the container name will match the node name - `n1`.

Note

Even when you change the prefix, the lab directory is still uniformly named using the `clab-<lab-name>` pattern.

### Topology[#](https://containerlab.dev/manual/topo-def-file/#topology "Permanent link")

The topology object inside the topology definition is the core element of the file. Under the `topology` element you will find all the main building blocks of a topology such as `nodes`, `kinds`, `defaults` and `links`.

#### Nodes[#](https://containerlab.dev/manual/topo-def-file/#nodes "Permanent link")

As with every other topology the nodes are in the center of things. With nodes we define which lab elements we want to run, in what configuration and flavor.

Let's zoom into the two nodes we have defined in our topology:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-4-1)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-4-2)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-4-3)    srl:                    # this is a name of the 1st node
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-4-4)      kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-4-5)      type: ixr-d2l
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-4-6)      image: ghcr.io/nokia/srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-4-7)    ceos:                   # this is a name of the 2nd node
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-4-8)      kind: arista_ceos
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-4-9)      image: ceos:4.32.0F
    

We defined individual nodes under the `topology.nodes` container. The name of the node is the key under which it is defined. Following the example, our two nodes are named `srl` and `ceos` respectively.

Each node can have multiple configuration properties which make containerlab quite a flexible tool. The `srl` node in our example is defined with the a few node-specific properties:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-5-1)srl:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-5-2)  kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-5-3)  type: ixr-d2l
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-5-4)  image: ghcr.io/nokia/srlinux
    

Refer to the [node configuration](https://containerlab.dev/manual/nodes/) document to meet all other options a node can have.

#### Links[#](https://containerlab.dev/manual/topo-def-file/#links "Permanent link")

Although it is absolutely fine to define a node without any links (like in [this lab](https://containerlab.dev/lab-examples/single-srl/)), we usually interconnect the nodes to make topologies. One of containerlab purposes is to make the interconnection of the nodes simple.

Links are defined under the `topology.links` section of the topology file. Containerlab understands two formats of link definition - brief and extended.  
A brief form of a link definition compresses link parameters in a single string and provide a quick way to define a link at the cost of link features available.  
A more expressive extended form exposes all link features, but requires more typing if done manually. The extended format is perfect for machine-generated link topologies.

##### Interface naming[#](https://containerlab.dev/manual/topo-def-file/#interface-naming "Permanent link")

Containerlab supports two kinds of interface naming: Linux interfaces[2](https://containerlab.dev/manual/topo-def-file/#fn:2) and interface aliases.

The "raw" Linux interface names are the names of the interfaces as they are expected to be seen **inside** the container (but not necessarily how they look like in the configuration file). Have a look at this topology that features SR Linux and cEOS nodes interconnected with a single link using Linux interface names:

using Linux interface names
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-6-1)# nodes configuration omitted for clarity
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-6-2)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-6-3)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-6-4)    srl:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-6-5)    ceos:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-6-6)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-6-7)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-6-8)    - endpoints: ["srl:e1-2", "ceos:eth2"] [](https://containerlab.dev/manual/topo-def-file/#__code_6_annotation_1)
    

  1. 


###### Aliases[#](https://containerlab.dev/manual/topo-def-file/#aliases "Permanent link")

The downside of using Linux interface names is that they often do not match the interface naming convention used by the Network OS. This is where Interface Aliases feature (added in Containerlab v0.56.0) comes in handy. Imagine we want to create a lab with four different Kinds: SR Linux, vEOS, CSR1000v and vSRX, cabled like this:

A side | B side  
---|---  
SR Linux ethernet-1/1 | vEOS Ethernet1/1  
vSRX ge-0/0/2 | vEOS Ethernet1/2  
CSR1000v Gi5 | vSRX ge-0/0/5  
vEOS Ethernet1/3 | CSR1000v Gi3  
  
[Using Linux interfaces](https://containerlab.dev/manual/topo-def-file/#__tabbed_2_1)[Using interface aliases](https://containerlab.dev/manual/topo-def-file/#__tabbed_2_2)

Using the `ethX` interface naming convention, the topology would look like this:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-7-1)links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-7-2)  - endpoints: ["srl:e1-1", "vEOS:eth1"]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-7-3)  - endpoints: ["vSRX:eth3", "vEOS:eth2"]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-7-4)  - endpoints: ["CSR1000v:eth4", "vSRX:eth6"]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-7-5)  - endpoints: ["vEOS:eth3", "CSR1000v:eth2"]
    

Note the four different kinds of offset used here on the four different NOSes!

Using aliased interface names, the topology definition becomes much more straightforward:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-8-1)links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-8-2)  - endpoints: ["srl:ethernet-1/1", "vEOS:Ethernet1/1"]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-8-3)  - endpoints: ["vSRX:ge-0/0/2", "vEOS:Ethernet1/2"]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-8-4)  - endpoints: ["CSR1000v:Gi5", "vSRX:ge-0/0/5"]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-8-5)  - endpoints: ["vEOS:Ethernet1/3", "CSR1000v:Gi3"]
    

Both topology definitions result in the same lab being deployed, but the latter is easier to write and to understand.

Many [Kinds](https://containerlab.dev/manual/kinds/) (but not all) support interface aliases and the alias names are provided in the respective kind' documentation.

Containerlab transparently maps from interface aliases to Linux interface names, and there's no additional syntax or configuration needed to specify either an interface alias or a Linux interface name in topologies.

How do aliases work?

Internally, interface aliases end up being deterministically mapped to Linux interface names, which conform to Linux interface naming standards: at most 15 characters, spaces and forward slashes (`/`) not permitted.

Since many NOSes use long interface names (`GigabitEthernet1`, that's exactly 1 character longer than permitted), and like to use slashes in their interface naming conventions, these NOS interface names cannot be directly used as interface names for the container interfaces created by Containerlab.  
For example, SR Linux maps its `ethernet-1/2` interface to the Linux interface `e1-2`. On the other hand, Juniper vSRX maps its `ge-0/0/1` interface to `eth2`.

##### Brief format[#](https://containerlab.dev/manual/topo-def-file/#brief-format "Permanent link")

The brief format of link definition looks as follows.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-9-1)# nodes configuration omitted for clarity
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-9-2)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-9-3)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-9-4)    srl:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-9-5)    ceos:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-9-6)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-9-7)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-9-8)    - endpoints: ["srl:ethernet-1/1", "ceos:Ethernet1/1"] [](https://containerlab.dev/manual/topo-def-file/#__code_9_annotation_1)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-9-9)    - endpoints: ["srl:e1-2", "ceos:eth2"]
    

  1. 


As you see, the `topology.links` element is a list of individual links. The link itself is expressed as pair of `endpoints`. This might sound complicated, lets use a graphical explanation:

topology:

  nodes:

    ceos:

    srl:

  


  links:

    \- endpoints: ["srl:ethernet1/1", "ceos:Ethernet1/1"]

    \- endpoints: ["srl:e1-2", "ceos:eth2"]

links

linux interface name

endpoint

srl

ceos

e1-1

eth1

e1-2

eth2

interface alias name

As demonstrated on a diagram above, the links between the containers are the point-to-point links which are defined by a pair of interfaces. The link defined as:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-10-1)endpoints: ["srl:e1-1", "ceos:eth1"]
    

will result in a creation of a p2p link between the node named `srl` and its `e1-1` interface and the node named `ceos` and its `eth1` interface. The p2p link is realized with a veth pair.

##### Extended format[#](https://containerlab.dev/manual/topo-def-file/#extended-format "Permanent link")

The extended link format allows a user to set every supported link parameter in a structured way. The available link parameters depend on the Link type and provided below.

###### veth[#](https://containerlab.dev/manual/topo-def-file/#veth "Permanent link")

The veth link is the most common link type used in containerlab. It creates a virtual ethernet link between two endpoints where each endpoint refers to a node in the topology.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-1)links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-2)  - type: veth
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-3)    endpoints:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-4)      - node: <NodeA-Name>                  # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-5)        interface: <NodeA-Interface-Name>   # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-6)        mac: <NodeA-Interface-Mac>          # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-7)        ipv4: <NodeA-IPv4-Address>          # optional e.g. 192.168.0.1/24
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-8)        ipv6: <NodeA-IPv6-Address>          # optional e.g. 2001:db8::1/64
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-9)      - node: <NodeB-Name>                  # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-10)        interface: <NodeB-Interface-Name>   # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-11)        mac: <NodeB-Interface-Mac>          # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-12)        ipv4: <NodeB-IPv4-Address>          # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-13)        ipv6: <NodeB-IPv6-Address>          # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-14)    mtu: <link-mtu>                         # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-15)    vars: <link-variables>                  # optional (used in templating)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-11-16)    labels: <link-labels>                   # optional (used in templating)
    

###### mgmt-net[#](https://containerlab.dev/manual/topo-def-file/#mgmt-net "Permanent link")

The mgmt-net link type represents a veth pair that is connected to a container node on one side and to the management network (usually a bridge) instantiated by the container runtime on the other.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-12-1)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-12-2)  - type: mgmt-net
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-12-3)    endpoint:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-12-4)      node: <NodeA-Name>                    # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-12-5)      interface: <NodeA-Interface-Name>     # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-12-6)      mac: <NodeA-Interface-Mac>            # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-12-7)    host-interface: <interface-name>        # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-12-8)    mtu: <link-mtu>                         # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-12-9)    vars: <link-variables>                  # optional (used in templating)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-12-10)    labels: <link-labels>                   # optional (used in templating)
    

The `host-interface` is the desired interface name that will be attached to the management network in the host namespace.

###### macvlan[#](https://containerlab.dev/manual/topo-def-file/#macvlan "Permanent link")

The macvlan link type creates a MACVlan interface with the `host-interface` as its parent interface. The MACVlan interface is then moved to a node's network namespace and renamed to the `endpoint.interface` name.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-13-1)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-13-2)  - type: macvlan
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-13-3)    endpoint:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-13-4)      node: <NodeA-Name>                  # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-13-5)      interface: <NodeA-Interface-Name>   # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-13-6)      mac: <NodeA-Interface-Mac>          # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-13-7)    host-interface: <interface-name>        # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-13-8)    mode: <macvlan-mode>                    # optional ("bridge" by default)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-13-9)    vars: <link-variables>                  # optional (used in templating)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-13-10)    labels: <link-labels>                   # optional (used in templating)
    

The `host-interface` is the name of the existing interface present in the host namespace.

[Modes](https://man7.org/linux/man-pages/man8/ip-link.8.html) are `private`, `vepa`, `bridge`, `passthru` and `source`. The default is `bridge`.

###### host[#](https://containerlab.dev/manual/topo-def-file/#host "Permanent link")

The host link type creates a veth pair between a container and the host network namespace.  
In comparison to the veth type, no bridge or other namespace is required to be referenced in the link definition for a "remote" end of the veth pair.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-14-1)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-14-2)  - type: host
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-14-3)    endpoint:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-14-4)      node: <NodeA-Name>                  # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-14-5)      interface: <NodeA-Interface-Name>   # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-14-6)      mac: <NodeA-Interface-Mac>          # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-14-7)    host-interface: <interface-name>        # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-14-8)    mtu: <link-mtu>                         # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-14-9)    vars: <link-variables>                  # optional (used in templating)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-14-10)    labels: <link-labels>                   # optional (used in templating)
    

The `host-interface` parameter defines the name of the veth interface in the host's network namespace.

###### vxlan[#](https://containerlab.dev/manual/topo-def-file/#vxlan "Permanent link")

The vxlan type results in a vxlan tunnel interface that is created in the host namespace and subsequently pushed into the nodes network namespace.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-1)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-2)    - type: vxlan
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-3)      endpoint:                              # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-4)        node: <Node-Name>                    # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-5)        interface: <Node-Interface-Name>     # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-6)        mac: <Node-Interface-Mac>            # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-7)      remote: <Remote-VTEP-IP>               # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-8)      vni: <VNI>                             # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-9)      dst-port: <VTEP-UDP-Port>              # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-10)      src-port: <Source-UDP-Port>            # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-11)      mtu: <link-mtu>                        # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-12)      vars: <link-variables>                 # optional (used in templating)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-15-13)      labels: <link-labels>                  # optional (used in templating)
    

###### vxlan-stitched[#](https://containerlab.dev/manual/topo-def-file/#vxlan-stitched "Permanent link")

The vxlan-stitched type results in a veth pair linking the host namespace and the nodes namespace and a vxlan tunnel that also terminates in the host namespace. In addition to these interfaces, tc rules are being provisioned to stitch the vxlan tunnel and the host based veth interface together.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-1)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-2)    - type: vxlan-stitch
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-3)      endpoint:                              # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-4)        node: <Node-Name>                    # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-5)        interface: <Node-Interface-Name>     # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-6)        mac: <Node-Interface-Mac>            # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-7)      remote: <Remote-VTEP-IP>               # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-8)      vni: <VNI>                             # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-9)      dst-port: <VTEP-UDP-Port>              # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-10)      src-port: <Source-UDP-Port>            # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-11)      mtu: <link-mtu>                        # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-12)      vars: <link-variables>                 # optional (used in templating)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-16-13)      labels: <link-labels>                  # optional (used in templating)
    

###### dummy[#](https://containerlab.dev/manual/topo-def-file/#dummy "Permanent link")

The dummy type creates a dummy interface that provides a virtual network device to route packets through without actually transmitting them.

Such interfaces are useful for testing and debugging purposes where we want to make sure that the NOS detects network ports, but doesn't actually need to send or receive packets via these ports.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-17-1)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-17-2)  - type: dummy
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-17-3)    endpoint:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-17-4)      node: <NodeA-Name>                    # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-17-5)      interface: <NodeA-Interface-Name>     # mandatory
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-17-6)      mac: <NodeA-Interface-Mac>            # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-17-7)    mtu: <link-mtu>                         # optional
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-17-8)    vars: <link-variables>                  # optional (used in templating)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-17-9)    labels: <link-labels>                   # optional (used in templating)
    

##### Variables[#](https://containerlab.dev/manual/topo-def-file/#variables "Permanent link")

Link variables are a way to supply additional link-related information that can be passed to the configuration templates and will be rendered in the [topology data](https://containerlab.dev/manual/inventory/#topology-data) json file.

You can provide link variables using link's brief and extended format. When using the brief format, the vars are defined under the link map and they will be available under the link container in the topology json file:

[brief format](https://containerlab.dev/manual/topo-def-file/#__tabbed_3_1)[topology data file](https://containerlab.dev/manual/topo-def-file/#__tabbed_3_2)
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-18-1)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-18-2)    - endpoints: [srl1:e1-1, srl2:e1-1]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-18-3)      vars:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-18-4)        foo: bar
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-18-5)        baz:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-18-6)          - one
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-18-7)          - two
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-18-8)          - three
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-18-9)        three:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-18-10)          a: b
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-18-11)          c: d
    
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-1)"links": [
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-2)  {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-3)    "endpoints": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-4)      "a": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-5)        "node": "srl1",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-6)        "interface": "e1-1",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-7)        "mac": "aa:c1:ab:12:bb:44",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-8)        "peer": "z"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-9)      },
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-10)      "z": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-11)        "node": "srl2",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-12)        "interface": "e1-1",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-13)        "mac": "aa:c1:ab:96:1c:d1",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-14)        "peer": "a"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-15)      }
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-16)    },
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-17)    "vars": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-18)      "baz": [
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-19)        "one",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-20)        "two",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-21)        "three"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-22)      ],
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-23)      "foo": "bar",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-24)      "three": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-25)        "a": "b",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-26)        "c": "d"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-27)      }
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-28)    }
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-29)  }
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-19-30)]
    

In the extended format, the vars can be defined for the entire link or for each endpoint individually.

[extended format](https://containerlab.dev/manual/topo-def-file/#__tabbed_4_1)[topology data file](https://containerlab.dev/manual/topo-def-file/#__tabbed_4_2)
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-1)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-2)    - type: veth
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-3)      endpoints:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-4)        - node: srl1
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-5)          interface: e1-2
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-6)          vars:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-7)            srl1ep1var1: "val1"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-8)            srl1ep1var2:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-9)              a: "b"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-10)              c: "d"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-11)            srl1ep1var3:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-12)              - "x"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-13)              - "y"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-14)              - "z"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-15)        - node: srl2
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-16)          interface: e1-2
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-17)          vars:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-18)            srl2ep1var1: "val2"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-19)            srl2ep1var2:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-20)              x: "y"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-21)              z: "a"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-22)            srl2ep1var3:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-23)              - 1
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-24)              - 2
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-20-25)              - 3
    
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-1)  "links": [
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-2)    {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-3)      "endpoints": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-4)        "a": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-5)          "node": "srl1",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-6)          "interface": "e1-2",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-7)          "mac": "aa:c1:ab:56:36:28",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-8)          "vars": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-9)            "srl1ep1var1": "val1",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-10)            "srl1ep1var2": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-11)              "a": "b",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-12)              "c": "d"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-13)            },
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-14)            "srl1ep1var3": [
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-15)              "x",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-16)              "y",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-17)              "z"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-18)            ]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-19)          },
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-20)          "peer": "z"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-21)        },
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-22)        "z": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-23)          "node": "srl2",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-24)          "interface": "e1-2",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-25)          "mac": "aa:c1:ab:09:2f:ea",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-26)          "vars": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-27)            "srl2ep1var1": "val2",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-28)            "srl2ep1var2": {
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-29)              "x": "y",
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-30)              "z": "a"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-31)            },
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-32)            "srl2ep1var3": [
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-33)              1,
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-34)              2,
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-35)              3
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-36)            ]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-37)          },
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-38)          "peer": "a"
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-39)        }
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-40)      }
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-41)    }
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-21-42)  ]
    

##### IP Addresses[#](https://containerlab.dev/manual/topo-def-file/#ip-addresses "Permanent link")

The `ipv4` and `ipv6` fields allow for you to set the IPv4 and/or IPv6 address on an interface respectively; directly from the topology file.

Note

Currently only the [Nokia SR Linux](https://containerlab.dev/manual/kinds/srl/) and [Cisco IOL](https://containerlab.dev/manual/kinds/cisco_iol/) kind(s) support this feature. Contributions to add support for other kinds are welcomed.

Refer to the below example, where we configure some addressing on the node interfaces using the [brief](https://containerlab.dev/manual/topo-def-file/#brief-format) format where addresses are passed as an ordered list matching the order of which the endpoint interfaces are defined.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-1)name: ip-addr-brief
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-2)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-3)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-4)    srl1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-5)      kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-6)      image: ghcr.io/nokia/srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-7)    srl2:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-8)      kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-9)      image: ghcr.io/nokia/srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-10)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-11)    - endpoints: ["srl1:e1-1", "srl2:e1-1"]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-12)      ipv4: ["192.168.0.1/24", "192.168.0.2/24"]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-13)      ipv6: ["2001:db8::1/64", "2001:db8::2/64"]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-14)    - endpoints: ["srl1:e1-2", "srl2:e1-2"]
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-22-15)      ipv4: ["192.168.2.1/24"] [](https://containerlab.dev/manual/topo-def-file/#__code_22_annotation_1)
    

  1. 


The [extended](https://containerlab.dev/manual/topo-def-file/#extended-format) format also supports providing the variables, in a more structured way:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-1)name: ip-vars-extended
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-2)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-3)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-4)    srl1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-5)      kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-6)      image: ghcr.io/nokia/srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-7)    srl2:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-8)      kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-9)      image: ghcr.io/nokia/srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-10)  links:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-11)    - type: veth
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-12)      endpoints:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-13)        - node: srl1
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-14)          interface: e1-2
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-15)          ipv4: 192.168.0.1/24
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-16)          ipv6: 2001:db8::1/64
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-17)        - node: srl2
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-18)          interface: e1-2
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-19)          ipv4: 192.168.0.2/24
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-20)          ipv6: 2001:db8::2/64
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-21)    - type: veth
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-22)      endpoints:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-23)        - node: srl1
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-24)          interface: e1-2
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-25)          ipv4: 192.168.2.1/24
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-26)        - node: srl2
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-23-27)          interface: e1-2
    

In both examples, we configure the `192.168.0.0/24`, and `2001:db8::/64` subnets on the link between srl1 and srl2's `e1-1` interfaces, where the least significant value represents the host, `1` for srl1, and `2` for srl2.

We can also set the IP for only one side, which is shown using IPv4 as an example on the link between srl1 and srl2 on the `e1-2` interfaces. Where the IPv4 address `192.168.2.1` is only set for `srl1`.

#### Groups[#](https://containerlab.dev/manual/topo-def-file/#groups "Permanent link")

`groups` sets the values for the properties of all nodes belonging to the group that you define, it's more flexible than `kinds` which only sets the properties for nodes of that specific kind.

It is useful to organise your topology, especially in cases where nodes of the same kind may require differing properties such as `type` or image version.

Values inherited from `groups` will take precedence over `kinds` and `defaults`. In other words, the inheritance model is as follows (from most specific to less specific):
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-24-1)node -> group -> kind -> defaults
    

For example, the We create separate groups for debian and alpine clients, as well as a group for spines where the nodes will be of type `ixrd3l`.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-1)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-2)  defaults:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-3)    kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-4)    image: ghcr.io/nokia/srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-5)  groups:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-6)    spines:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-7)      type: ixrd3l
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-8)    apline-clients:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-9)      kind: linux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-10)      image: alpine
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-11)    debian-clients:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-12)      kind: linux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-13)      image: debian
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-14)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-15)    srl1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-16)      group: spines
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-17)    srl2:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-18)      group: spines
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-19)    srl3:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-20)    srl4:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-21)    client1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-22)      group: alpine-clients
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-23)    client2:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-24)      group: alpine-clients
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-25)    client3:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-26)      group: debian-clients
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-27)    client4:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-25-28)      group: debian-clients
    

Now with the above example, we can notice:

  * The client nodes in the `alpine-clients` group will be `linux` kind and run the `alpine` image.
  * The client nodes in the `debian-clients` group will be `linux` kind and run the `debian` image.
  * The nodes in the `spines` group will be `ixrd3l` chassis, but still inherit the kind and image from defaults.
  * The `srl3` and `srl4` don't belong to any group, so they will inherit their properties from the `defaults`.



#### Kinds[#](https://containerlab.dev/manual/topo-def-file/#kinds "Permanent link")

Kinds define the behavior and the nature of a node, it says if the node is a specific containerized Network OS, virtualized router or something else. We go into details of kinds in its own [document section](https://containerlab.dev/manual/kinds/), so here we will discuss what happens when `kinds` section appears in the topology definition:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-1)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-2)  kinds:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-3)    nokia_srlinux:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-4)      type: ixr-d2l
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-5)      image: ghcr.io/nokia/srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-6)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-7)    srl1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-8)      kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-9)    srl2:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-10)      kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-11)    srl3:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-26-12)      kind: nokia_srlinux
    

In the example above the `topology.kinds` element has `nokia_srlinux` kind referenced. With this, we set some values for the properties of the `nokia_srlinux` kind. A configuration like that says that nodes of `nokia_srlinux` kind will also inherit the properties (type, image) defined on the _kind level_.

Essentially, what `kinds` section allows us to do is to shorten the lab definition in cases when we have a number of nodes of a same kind. All the nodes (`srl1`, `srl2`, `srl3`) will have the same values for their `type` and `image` properties.

Consider how the topology would have looked like without setting the `kinds` object:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-1)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-2)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-3)    srl1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-4)      kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-5)      type: ixr-d2l
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-6)      image: ghcr.io/nokia/srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-7)    srl2:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-8)      kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-9)      type: ixr-d2l
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-10)      image: ghcr.io/nokia/srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-11)    srl3:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-12)      kind: nokia_srlinux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-13)      type: ixr-d2l
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-27-14)      image: ghcr.io/nokia/srlinux
    

A lot of unnecessary repetition is eliminated when we set `nokia_srlinux` kind properties on kind level.

#### Defaults[#](https://containerlab.dev/manual/topo-def-file/#defaults "Permanent link")

`kinds` set the values for the properties of a specific kind, whereas with the `defaults` container it is possible to set values globally.

For example, to set the environment variable for all the nodes of a topology:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-28-1)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-28-2)  defaults:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-28-3)    env:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-28-4)      MYENV: VALUE
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-28-5)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-28-6)    srl1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-28-7)    srl2:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-28-8)    srl3:
    

Now every node in this topology will have environment variable `MYENV` set to `VALUE`.

### Settings[#](https://containerlab.dev/manual/topo-def-file/#settings "Permanent link")

Global containerlab settings are defined in `settings` container. The following settings are supported:

#### Certificate authority[#](https://containerlab.dev/manual/topo-def-file/#certificate-authority "Permanent link")

Global certificate authority settings section allows users to tune certificate management in containerlab. Refer to the [Certificate management](https://containerlab.dev/manual/cert/) doc for more details.

## Environment variables[#](https://containerlab.dev/manual/topo-def-file/#environment-variables "Permanent link")

Topology definition file may contain environment variables anywhere in the file. The syntax is the same as in the bash shell:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-29-1)name: linux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-29-2)
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-29-3)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-29-4)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-29-5)    l1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-29-6)      kind: linux
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-29-7)      image: alpine:${ALPINE_VERSION:=3}
    

In the example above, the `ALPINE_VERSION` environment variable is used to set the version of the alpine image. If the variable is not set, the value of `3` will be used. The following syntax is used to expand the environment variable:

**Expression** | **Meaning**  
---|---  
`${var}` | Value of var (same as `$var`)  
`${var-$DEFAULT}` | If var not set, evaluate expression as $DEFAULT  
`${var:-$DEFAULT}` | If var not set or is empty, evaluate expression as $DEFAULT  
`${var=$DEFAULT}` | If var not set, evaluate expression as $DEFAULT  
`${var:=$DEFAULT}` | If var not set or is empty, evaluate expression as $DEFAULT  
`${var+$OTHER}` | If var set, evaluate expression as $OTHER, otherwise as empty string  
`${var:+$OTHER}` | If var set, evaluate expression as $OTHER, otherwise as empty string  
`$$var` | Escape expressions. Result will be `$var`.  
  
## Magic Variables[#](https://containerlab.dev/manual/topo-def-file/#magic-variables "Permanent link")

Magic variables are special strings that get replaced with actual values during the topology parsing.to make your lab configurations more dynamic and less verbose. These variables are surrounded by double underscores (`__variable__`) and can be seen in some of the advanced topology examples.

These variables can be used in startup-config paths, bind paths, and exec commands. They are replaced with actual values during lab deployment:

Variable | Description | Example Usage | Expands To  
---|---|---|---  
`__clabNodeName__` | Current node's short name | `startup-config: cfg/__clabNodeName__.cfg` | `cfg/node1.cfg` (for node named "node1")  
`__clabNodeDir__` | Path to the node's lab directory | `binds: __clabNodeDir__/conf:/conf` | `clab-mylab/node1/conf:/conf`  
`__clabDir__` | Path to the lab's main directory | `binds: __clabDir__/data.json:/data.json:ro` | `clab-mylab/data.json:/data.json:ro`  
  
Here are some practical examples when using magic variables can greatly simplify your topology definitions:

[Dynamic startup configuration](https://containerlab.dev/manual/topo-def-file/#__tabbed_5_1)[Node-specific and lab-wide file binds](https://containerlab.dev/manual/topo-def-file/#__tabbed_5_2)[Customized exec commands](https://containerlab.dev/manual/topo-def-file/#__tabbed_5_3)

A common pattern found in many labs is to have a separate startup configuration file for each node. For regular network nodes it can be provided using `startup-config` property, for Linux containers it is often done using the file binds.

Regardless of the target node, at the end of the day, these startup configuration files are often named after the node they belong to. Using `__clabNodeName__` magic variable, we can simplify the topology definition and avoid repeating the node names in the config file paths by setting the `startup-config` or `binds` property once in the `defaults` or `kinds` section and then containerlab will take care of resolving it to the actual node.

Consider the following example where we set the `startup-config` property in the `defaults` section:
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-30-1)name: mylab
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-30-2)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-30-3)  defaults:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-30-4)    startup-config: configs/__clabNodeName__.cfg
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-30-5)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-30-6)    router1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-30-7)    router2:
    

Both `router1` and `router2` nodes will get their own startup configuration files: `configs/router1.cfg` and `configs/router2.cfg` respectively.

Using the `__clabNodeDir__` and `__clabDir__` magic variables, it is possible to bind node-specific files as well as lab-wide shared files into the nodes.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-31-1)name: mylab
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-31-2)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-31-3)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-31-4)    node1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-31-5)      binds:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-31-6)        # Node-specific files
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-31-7)        - __clabNodeDir__/custom.conf:/etc/custom.conf
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-31-8)        # Lab-wide shared files
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-31-9)        - __clabDir__/shared-data.json:/shared.json:ro
    

Another popular use case for the `__clabNodeName__` magic variable is to customize the `exec` commands on a per-node basis.
    
    
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-32-1)name: mylab
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-32-2)topology:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-32-3)  nodes:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-32-4)    node1:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-32-5)      exec:
    [](https://containerlab.dev/manual/topo-def-file/#__codelineno-32-6)        - echo "Node __clabNodeName__ started"  # Will output "Node node1 started"
    

## Generated topologies[#](https://containerlab.dev/manual/topo-def-file/#generated-topologies "Permanent link")

To further simplify parametrization of the topology files, containerlab allows users to template the topology files using Go Template engine.

Using templating approach it is possible to create a lab template and instantiate different labs from it, by simply changing the variables in the variables file.

To help you get started, we created the following lab examples which demonstrate how topology templating can be used:

  * [Leaf-Spine topology with parametrized number of leaves/spines](https://containerlab.dev/lab-examples/templated01/)
  * [5-stage Clos topology with parametrized number of pods and super-spines](https://containerlab.dev/lab-examples/templated02/)



* * *

  1. if the filename has `.clab.yml` or `-clab.yml` suffix, the YAML file will have autocompletion and linting support in VSCode editor. [↩](https://containerlab.dev/manual/topo-def-file/#fnref:1 "Jump back to footnote 1 in the text")

  2. also referred to as "mapped" or "raw" interfaces in some parts of the documentation [↩](https://containerlab.dev/manual/topo-def-file/#fnref:2 "Jump back to footnote 2 in the text")




* * *

* * *

Back to top 

[Cookie settings](https://containerlab.dev/manual/topo-def-file/#__consent)

Made with  by [ Containerlab team ](https://github.com/srl-labs/containerlab/graphs/contributors)

[ ](https://github.com/hellt "github.com") [ ](https://bsky.app/profile/containerlab.dev "bsky.app") [ ](https://discord.gg/vAyddtaEV9 "discord.gg")

#### Cookie consent

We use cookies to recognize your repeated visits and preferences, as well as to measure the effectiveness of our documentation and whether users find what they're searching for. With your consent, you're helping us to make our documentation better.

  * Google Analytics 
  * GitHub 



Accept Manage settings Reject
