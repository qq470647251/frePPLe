/*
 * Copyright (C) 2017 by frePPLe bvba
 *
 * This library is free software; you can redistribute it and/or modify it
 * under the terms of the GNU Affero General Public License as published
 * by the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
 * General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 */

'use strict';

angular.module('operationplandetailapp').directive('showproblemspanelDrv', showproblemspanelDrv);

showproblemspanelDrv.$inject = ['$window'];

function showproblemspanelDrv($window) {

  var directive = {
    restrict: 'EA',
    scope: {operationplan: '=data'},
    link: linkfunc
  };
  return directive;

  function linkfunc(scope, elem, attrs) {
    var rows='';
    var template = '<table class="table"><thead><tr><td>' +
                      '<b style="text-transform: capitalize;">'+gettext("problems")+'</b>' +
                    '</td><td>' +
                      '<b style="text-transform: capitalize;">'+gettext("start")+'</b>' +
                    '</td><td>' +
                      '<b style="text-transform: capitalize;">'+gettext("end")+'</b>' +
                    '</td></tr></thead>' +
                    '<tbody></tbody>' +
                  '</table>';

    scope.$watchGroup(['operationplan.id','operationplan.problems.length'], function (newValue,oldValue) {
      angular.element(document).find('#attributes-operationproblems').empty().append(template);
      var rows = '<tr><td colspan="3">'+gettext('no problems')+'<td></tr>';

      if (typeof scope.operationplan !== 'undefined') {
        if (scope.operationplan.hasOwnProperty('problems')) {
          rows='';
          angular.forEach(scope.operationplan.problems, function(theproblem) {
            rows += '<tr><td>'+
            theproblem.description+'</td>'+
            theproblem.start+'<td></td>'+
            theproblem.end+'<td></tr>';
          });
        }
      }
      angular.element(document).find('#attributes-operationproblems tbody').append(rows);
      //elem.after(transclude());
    }); //watch end

  } //link end
} //directive end
